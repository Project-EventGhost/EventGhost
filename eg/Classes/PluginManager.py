# -*- coding: utf-8 -*-
#
# This file is part of EventGhost.
# Copyright © 2005-2016 EventGhost Project <http://www.eventghost.org/>
#
# EventGhost is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 2 of the License, or (at your option)
# any later version.
#
# EventGhost is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
# more details.
#
# You should have received a copy of the GNU General Public License along
# with EventGhost. If not, see <http://www.gnu.org/licenses/>.

import os
import os.path
import shutil
import sys
import tempfile
import xml.parsers.expat
from copy import copy
from os.path import exists, isdir, join
from zipfile import BadZipfile

import requests
import wx
import wx.html
import wx.html2
import wx.lib.newevent
import wx.richtext
import xmltodict
from pkg_resources import parse_version

import eg


class Text(eg.TranslatableStrings):
    Author = "Author"
    AvailableVersion = "Available version"
    Changelog = "Changelog"
    Downgrade = \
        "Are you sure you want to downgrade the " \
        "plugin to the latest available version? " \
        "The installed one is newer!"
    ErrorBrokenPlugin = "This plugin is broken."
    ErrorConnectingRepo = "Couldn't connect to repository:"
    ErrorIncompatible1 = \
        "This plugin is incompatible with this version of {0}.\n"
    ErrorIncompatible2 = "The Plugin is designed for {0} {1}."
    ErrorMissingModule = "This plugin requires a missing module."
    ErrorParsingRepoData = "Error while parsing data from repository."
    ErrorReadingRepo = "Error reading repository: {0}\n\n{1}"
    ErrorWrongFormat = \
        "Data from repository has wrong format.\n" \
        "Missing Key:"
    FetchingRepos = "fetching repositories..."
    FileCorrupt = "Downloaded file is corrupted!\n" \
                  "The plugin will not be installed."
    In = "in"
    InstalledVersion = "Installed version"
    NewPluginsAvailable = (
        "There are {0} new plugins {1} upgradeable plugins available.\n"
        "You can install and get information about them in "
        "the Add Plugin Dialog."
    )
    NewerPlugin = \
        "Installed version of this plugin is higher than" \
        " any version found in repository"
    NewPlugin = "This is a new plugin"
    NewVersionAvailable = "There is a new version available"
    NoNewUpdatedPlugins = "No new or updated plugins available."
    NoDetails = "No details available"
    NotAvailable = \
        "Warning: this plugin isn't available in any accessible " \
        "repository!\nAre you sure you want to uninstall plugin\n" \
        "'{0}' (version {1})?"
    ObsoletePlugin = \
        "Obsolete plugin:\n{0}\n\n" \
        "EventGhost has detected an obsolete plugin that masks " \
        "its more recent version shipped with this copy of " \
        "EventGhost. Do you want to remove the old plugin right " \
        "now and unmask the more recent version?"
    OfficialRepoName = "Official EventGhost Plugin Repository"
    PluginRemoveFailed = \
        "Removing plugin failed!\n" \
        "Path: {0}\n" \
        "Function: {1}\n" \
        "Exception information:\n{2}"
    PluginStatusAmbiguous1 = "Error: plugin status is ambiguous (1)"
    PluginStatusAmbiguous2 = \
        "Error: plugin status is ambiguous (2)" \
        "\n-----------------------------------------------" \
        "\nplugin: {0} ({1})" \
        "\nself.plugin_cache[key].status = {2}" \
        "\nself.plugin_cache[key].installed = {3}"
    Removed = "Plugin '{0}' was removed successfully."
    Success = \
        "Plugin '{0}' was successfully installed.\n" \
        "Now you can add it to your configuration tree."

    class Dialog:
        Intervall_0 = "on every call of PluginManager"
        Intervall_1 = "once a day"
        Intervall_3 = "every 3 days"
        Intervall_7 = "every week"
        Intervall_14 = "every 2 weeks"
        Intervall_30 = "every month"
        LabelAllPlugins = "All plugins"
        LabelCheckUpdates = "Check for plugin updates"
        LabelDowngradePlugin = "Downgrade Plugin"
        LabelInstall = "Install plugin"
        LabelInstalled = "Installed plugins"
        LabelInstallPlugin = "Install Plugin"
        LabelNotInstalled = "Not installed plugins"
        LabelPagePlugins = "Plugins"
        LabelPageSettings = "Settings"
        LabelreinstallPlugin = "Reinstall Plugin"
        LabelUninstall = "Uninstall plugin"
        LabelUpgradeable = "Upgradeable plugins"
        LabelUpgradePlugin = "Upgrade Plugin"
        LabelUpgradeAll = "Updgrade all"
        LabelNew = "New plugins"
        LabelInvalid = "Invalid plugins"
        InfoUpdateCheck = (
            "If this function is enabled, EventGhost will inform you on "
            "startup whenever a new plugin or a plugin update is available."
        )


REPOSITORY_URL = "http://eg-plugins.torsti.net/plugins.php"


def remove_plugin_dir(path, parent=None):
    if not os.path.exists(path):
        return  # Nothing to remove
    else:
        def onError(function, path, excinfo):
            eg.MessageBox(egtext.PluginRemoveFailed.format(
                repr(path), repr(function), repr(excinfo)),
                style=wx.OK | wx.ICON_ERROR
            )
        shutil.rmtree(path, onerror=onError)


class ActionsMapping(object):
    def __init__(self, info):
        self.info = info
        self.actions = {}

    def __getitem__(self, name):
        if name in self.actions:
            return self.actions[name]

        class Action(eg.ActionBase):
            pass
        Action.__name__ = name
        action = self.info.actionGroup.AddAction(Action, hidden=True)
        self.actions[name] = action
        return action

    def __setitem__(self, name, value):
        self.actions[name] = value


class LoadErrorPlugin(eg.PluginBase):
    def __init__(self):
        raise self.Exceptions.PluginLoadError

    def __start__(self, *dummyArgs):
        raise self.Exceptions.PluginLoadError


class NonexistentPlugin(eg.PluginBase):
    class text:
        pass

    def __init__(self):
        raise self.Exceptions.PluginNotFound

    def __start__(self, *dummyArgs):
        raise self.Exceptions.PluginNotFound

    def GetLabel(self, *dummyArgs):
        return '<Unknown Plugin "%s">' % self.name


class NonexistentPluginInfo(eg.PluginInstanceInfo):
    def __init__(self, guid, name):
        self.guid = guid
        self.name = name
        self.pluginName = name

        class Plugin(NonexistentPlugin):
            pass

        Plugin.__name__ = name
        self.pluginCls = Plugin


class PluginCache(object):

    @eg.LogIt
    def __init__(self):
        global egtext
        self.plugin_cache = {}  # list of plugins (local + repo)
        self.local_cache = {}  # list of local installed plugins
        self.repo_cache = {}  # list of plugins from repository
        self._update_seen = False
        self.ScanAllInstalledPlugins()

    @eg.LogIt
    def GetPluginInfo(self, ident):
        try:
            return self.local_cache[ident]
        except KeyError:
            for guid, info in self.local_cache.iteritems():
                if info.pluginName == ident:
                # if info.pluginName == ident:
                    return info
        return None

    @eg.LogItWithReturn
    def IsThereAnythingNew(self):
        """ return true if an upgradeable or new plugin detected """
        new_plugins = {"new": [], "upgradeable": []}
        for plugin_info in self.plugin_cache.values():
            if plugin_info.status in ["upgradeable", "new"]:
                new_plugins[plugin_info.status].append(plugin_info)
        return new_plugins

    @eg.LogIt
    def SearchPluginInfo(self, name):
        for guid in self.local_cache:
            if self.local_cache[guid].name == name:
                return guid
        return None

    @eg.LogIt
    def GetAvailableInfoList(self):
        """
        Get a list of all PluginInfo for all plugins that are available
        from the online repository.
        """
        infoList = [
            self.plugin_cache[guid] for guid in self.plugin_cache
            if self.plugin_cache[guid].status != "installed"
        ]
        infoList.sort(key=lambda pluginInfo: pluginInfo.name.lower())
        return infoList

    @eg.LogIt
    def GetInstalledInfoList(self):
        """
        Get a list of all PluginInfo for all plugins that are installed.
        """
        infoList = [
            self.plugin_cache[guid] for guid in self.plugin_cache
            if self.plugin_cache[guid].status in [
                "installed", "orphan", "upgradeable", "newer"
            ]
        ]
        infoList.sort(key=lambda pluginInfo: pluginInfo.name.lower())
        return infoList

    @eg.LogItWithReturn
    def GetGuidByUrl(self, name):
        """ Return first guid found for given url """
        plugins = [guid for guid in self.plugin_cache if self.plugin_cache[guid].download_url == name]
        if plugins:
            return plugins[0]
        return None

    @eg.LogIt
    def clearRepoCache(self):
        """ clears the repo cache before re-fetching repositories """
        self.repo_cache = {}

    @eg.LogIt
    def removeInstalledPlugin(self, key):
        """ remove given plugin from the local_cache """
        if key in self.local_cache:
            del self.local_cache[key]

    def ScanAllInstalledPlugins(self):
        """
        Scans the plugin directories to get all needed information for all
        installed plugins.
        """
        self.local_cache.clear()

        # scan through all directories in all plugin directories
        for root in eg.pluginDirs:
            for dirname in os.listdir(root):
                # filter out non-plugin names
                if dirname.startswith(".") or dirname.startswith("_"):
                    continue
                pluginDir = join(root, dirname)
                if not isdir(pluginDir):
                    continue
                if not exists(join(pluginDir, "__init__.py")):
                    continue
                plugin_info = eg.PluginModuleInfo(pluginDir)
                self.local_cache[plugin_info.guid] = plugin_info
        self.RebuildPluginCache()

    @eg.LogIt
    def RebuildPluginCache(self):
        """ build or rebuild the plugin_cache from the caches """
        self.plugin_cache = {}
        for guid in self.local_cache:
            self.plugin_cache[guid] = copy(self.local_cache[guid])
        for repo_plugin in self.repo_cache.itervalues():
            # do not update repo_cache elements!
            plugin = copy(repo_plugin)
            guid = plugin.guid

            # check if the plugin is allowed and if there isn't
            # any better one added already.
            already_in_plugin_cache = guid in self.plugin_cache

            version_available = parse_version(plugin.versionAvailable)

            newer_version_available = False
            if already_in_plugin_cache:
                ver_in_cache = parse_version(
                    self.plugin_cache[guid].version
                )
                newer_version_available = version_available > ver_in_cache
                #self.plugin_cache[guid].installed = True

            # Add the available one if not present yet or
            # update it if present already.
            if not already_in_plugin_cache:
                # just add a new plugin
                self.plugin_cache[guid] = plugin
            else:
                # Update local plugin in cache with remote metadata.
                # icon: only use remote data if local one not available.
                # Prefer local icon to avoid downloading.
                for attrib in ["icon"]:
                    if (
                        not getattr(self.plugin_cache[guid], attrib)
                        and getattr(plugin, attrib)
                    ):
                        setattr(
                            self.plugin_cache[guid],
                            attrib,
                            getattr(plugin, attrib)
                        )
                # other remote metadata is prefered:
                for attrib in [
                    "author",
                    "date_added",
                    "description",
                    "download_url",
                    "hardwareId",
                    "kind",
                    "name",
                    "url",
                    "versionAvailable",
                ]:
                    if getattr(plugin, attrib):
                        setattr(
                            self.plugin_cache[guid],
                            attrib,
                            getattr(plugin, attrib)
                        )
            # set status
            #
            # installed   available   status
            # ---------------------------------------
            # none        any         "not installed" (will be later checked if is "new")
            # any         none        "orphan"
            # same        same        "installed"
            # less        greater     "upgradeable"
            # greater     less        "newer"
            if not plugin.versionAvailable:
                self.plugin_cache[guid].status = "orphan"
            elif not guid in self.local_cache:
                self.plugin_cache[guid].status = "not installed"
            elif newer_version_available:
                self.plugin_cache[guid].status = "upgradeable"
            elif guid in self.local_cache:
                self.plugin_cache[guid].status = "installed"
            elif ver_in_cache > version_available:
                self.plugin_cache[guid].status = "newer"
            else:
                self.plugin_cache[guid].status = "unknown"

            # TODO: debug: test if the status match the "installed" tag:
            pt1 = (self.plugin_cache[guid].status in ["not installed"])
            if pt1 and guid in self.local_cache:
                raise Exception(egtext.PluginStatusAmbiguous1)
            pt1 = (self.plugin_cache[guid].status in
                   ["installed", "orphan", "upgradeable", "newer"]
                   )
            if pt1 and not guid in self.local_cache:
                msg = egtext.PluginStatusAmbiguous2.format(
                    self.plugin_cache[guid]["name"],
                    guid,
                    repr(self.plugin_cache[guid].status),
                    "-"
                )
                raise Exception(msg)
        self.MarkNewPlugins()

    def MarkNewPlugins(self):
        last_check = wx.DateTime_Today()
        if eg.config.lastUpdateCheckDatePlugins:
            last_check.ParseISODate(eg.config.lastUpdateCheckDatePlugins)
        for guid, plugin_info in self.repo_cache.iteritems():
            if self.plugin_cache[guid].status in ["installed", "upgradeable"]:
                continue
            plugin_added = wx.DateTime_Today()
            if plugin_info.__getattribute__("date_added"):
                plugin_added.ParseISODate(plugin_info.__getattribute__("date_added"))
            if last_check <= plugin_added:
                self.plugin_cache[guid].status = "new"
        eg.config.lastUpdateCheckDatePlugins = wx.DateTime_Today().FormatISODate()

    def GetDownloadUrl(self, guid):
        if self.plugin_cache[guid].download_url:
            return self.plugin_cache[guid].download_url

        repoUrl = REPOSITORY_URL
        url = repoUrl.rpartition("/")[0] + "/"
        url += self.plugin_cache[guid].name + "_"
        url += self.plugin_cache[guid].versionAvailable.replace(".", "_")
        url += ".egplugin"


class PluginManager:

    @eg.LogIt
    def __init__(self):
        self.plugins = PluginCache()
        self.repository = Repository(self.plugins)
        self.fetched_in_session = False

    def GetAvailableInfoList(self):
        return self.plugins.GetAvailableInfoList()

    def GetInstalledInfoList(self):
        return self.plugins.GetInstalledInfoList()

    def GetPluginInfo(self, guid):
        return self.plugins.GetPluginInfo(guid)

    def SearchPluginInfo(self, name):
        return self.plugins.SearchPluginInfo(name)

    @eg.LogIt
    def UpdateCheck(self, manually=False):
        self.repository.DoFetching()
        new_plugins = self.plugins.IsThereAnythingNew()
        if new_plugins["new"] or new_plugins["upgradeable"]:
            wx.CallAfter(self.NewPluginsAvailable, new_plugins)
            return
        if manually:
            eg.MessageBox(Text.NoNewUpdatedPlugins)

    def FetchIfNeeded(self):
        try:
            lastDate = self.repository.GetLastStartDay()
            diff = (wx.DateTime_Today() - lastDate).days
        except (ValueError, AssertionError):
            diff = 1
        if diff >= 1:
            self.repository.DoFetching()

    def NewPluginsAvailable(self, new_plugins):
        # TODO: option to install/upgrade directly
        msg = Text.NewPluginsAvailable.format(
            len(new_plugins["new"]),
            len(new_plugins["upgradeable"])
        )
        eg.MessageBox(msg, style=wx.OK | wx.ICON_INFORMATION)

    @eg.LogIt
    def OpenPlugin(self, guid, evalName, args, treeItem=None):
        moduleInfo = self.plugins.GetPluginInfo(guid)
        if moduleInfo is None:
            # we don't have that plugin
            # TODO: optionaly search for it in repository and give option
            #       to download the plugin
            clsInfo = NonexistentPluginInfo(guid, evalName)
        else:
            try:
                clsInfo = eg.PluginInstanceInfo.FromModuleInfo(moduleInfo)
            except eg.Exceptions.PluginLoadError:
                if evalName:
                    clsInfo = NonexistentPluginInfo(guid, evalName)
                else:
                    raise
        info = clsInfo.CreateInstance(args, evalName, treeItem)
        if moduleInfo is None:
            info.actions = ActionsMapping(info)
        return info

    @eg.LogIt
    def UpgradePlugin(self, guid):
        # TODO: make a backup before installing
        self.InstallPlugin(guid, True)

    @eg.LogIt
    def InstallPlugin(self, guid, quiet=False):
        """ Install given plugin """
        plugin_info = self.plugins.plugin_cache[guid]
        if not plugin_info:
            return
        if plugin_info.status == "newer":
            # ask for confirmation if user downgrades an usable plugin
            rc = eg.MessageBox(
                egtext.Downgrade,
                style=wx.YES | wx.CANCEL | wx.ICON_EXCLAMATION
            )
            if rc != wx.ID_YES:
                return

        downloadedFilePath = self.DownloadFile(plugin_info.download_url)
        try:
            rc = eg.PluginInstall.Import(downloadedFilePath, quiet)
        except BadZipfile:
            with open(downloadedFilePath, "rt") as f:
                txt = f.read()
            if txt.upper().startswith("<!DOCTYPE HTML"):
                eg.HtmlMessageBox(
                    txt.decode("utf8"),
                    style=wx.OK | wx.ICON_ERROR
                )
            else:
                eg.MessageBox(
                    "{0}\n{1}".format(
                        egtext.FileCorrupt,
                        repr(sys.exc_info())
                    ),
                    style=wx.OK | wx.ICON_ERROR
                )
            return
        if rc == wx.ID_CANCEL:
            return
        self.UpdatePluginCache()

    @eg.LogIt
    def UninstallPlugin(self, guid):
        """ Uninstall given plugin """
        actionItemCls = eg.document.ActionItem
        pluginItemCls = eg.document.PluginItem
        autostartItemCls = eg.document.AutostartItem

        def SearchFunc(obj):
            if obj.__class__ == actionItemCls:
                if obj.executable:
                    if obj.executable.plugin.info.guid == guid:
                        return True
            return None
        inUse = eg.document.root.Traverse(SearchFunc) is not None

        if not inUse:
            rmv = []
            def SearchFunc(obj):
                if obj.__class__ == pluginItemCls:
                    if obj.executable:
                        if obj.executable.info.guid == guid:
                            rmv.append(obj)
                return None
            eg.document.root.Traverse(SearchFunc)

            def dontAsk():
                return True

            if rmv:
                # The plugin isn't used in Macros, but is added to Autostart
                # folder in config tree.
                # If the plugin can multi load, for every item would come
                # up an confirmation dialog. Instead replace that function
                # and just ask one time.
                # TODO: Ask for comfirmation to delete
                for item in rmv:
                    item.AskDelete = dontAsk
                    eg.UndoHandler.Clear(eg.document).Do(item)

        if inUse:
            eg.MessageBox(parent=None,
                message=eg.text.General.deletePlugin,
                style=wx.NO_DEFAULT | wx.OK | wx.ICON_EXCLAMATION,
            )
            return

        if guid in self.plugins.plugin_cache:
            pluginInfo = self.plugins.plugin_cache[guid]
        else:
            pluginInfo = self.plugins.local_cache[guid]
        if not pluginInfo:
            return
        # TODO: check the following
        notAvailable = pluginInfo.status == "orphan"
        if notAvailable:
            rc = eg.MessageBox(
                egtext.NotAvailable.format(
                    pluginInfo.name, pluginInfo.version
                ),
                style=wx.NO_DEFAULT | wx.YES | wx.NO | wx.ICON_WARNING
            )
            if rc != wx.ID_YES:
                return

        remove_plugin_dir(self.plugins.local_cache[guid].path)
        self.UpdatePluginCache()

    @eg.LogIt
    def UpdatePluginCache(self):
        # update the plugin cache
        self.plugins.ScanAllInstalledPlugins()

    @eg.LogIt
    def DownloadFile(self, url):
        tmpFile = tempfile.mktemp()
        # NOTE: stream=True
        r = requests.get(url, stream=True)

        with open(tmpFile, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024):
                if chunk:  # filter out keep-alive new chunks
                    f.write(chunk)
        return tmpFile


class Repository(object):

    @eg.LogIt
    def __init__(self, plugins):
        self.plugins = plugins
        self._request = None

    @eg.LogItWithReturn
    def GetLastStartDay(self):
        # Settings may contain invalid value...
        day = wx.DateTime()
        try:
            ok = day.ParseISODate(eg.config.lastUpdateCheckDatePlugins)
        except TypeError:
            ok = False
        if ok:
            return day
        return wx.DateTime().Today()

    @eg.LogItWithReturn
    def IsTimeForChecking(self):
        """ determine whether it's the time for checking for news and updates now """
        if eg.config.checkUpdatePluginInterval == 0:
            return True
        try:
            lastDate = self.GetLastStartDay()
            interval = (wx.DateTime_Today() - lastDate).days
        except (ValueError, AssertionError):
            interval = 7
        return interval >= eg.config.checkUpdatePluginInterval

    @eg.LogIt
    def FetchRepository(self):
        if eg.config.checkUpdatePluginContinuous and self.IsTimeForChecking():
            self.DoFetching()

    @eg.LogIt
    def DoFetching(self):
        """ start fetching the repository """
        try:
            self._request = requests.get(
                REPOSITORY_URL,
                verify=True,
                timeout=10.0,
            )
        except requests.ConnectionError as err:
            eg.PrintError(
                "{0}\n{1}\n".format(
                    egtext.ErrorConnectingRepo,
                    REPOSITORY_URL
                )
            )
            return
        self.ParseDownloadedXml()
        self.plugins.RebuildPluginCache()
        eg.pluginManager.fetched_in_session = True

    @eg.LogIt
    def ParseDownloadedXml(self):
        """ populate the plugins object with the fetched data """

        try:
            x2d = xmltodict.parse(self._request.content)
        except xml.parsers.expat.ExpatError as err:
            eg.PrintError(
                "{0}\n({1})".format(
                    egtext.ErrorParsingRepoData, err.message
                )
            )
            return

        try:
            available_plugins = x2d["repository"]["plugins"]["egplugin"]
        except KeyError as err:
            eg.PrintError("{0} {1}".format(egtext.ErrorWrongFormat, err))
            return

        if not available_plugins:
            # no plugin metadata found
            return

        # clear the repository plugin cache
        self.plugins.repo_cache = dict()

        for plgn in available_plugins:
            plugin_info = eg.PluginModuleInfo("repo:{0}".format(plgn.get("guid")))
            try:
                plugin_info.RegisterPlugin(
                    author=plgn.get("author", u""),
                    description=plgn.get("description", u""),
                    guid=plgn.get("guid", ""),
                    hardwareId=plgn.get("hardware_id", ""),
                    icon=plgn.get("icon", None),
                    kind=plgn.get("kind", "other"),
                    name=plgn.get("name", u""),
                    url=plgn.get("url", ""),
                )
            except eg.Exceptions.RegisterPluginException:
                plugin_info.versionAvailable = plgn.get("version", "")
                plugin_info.download_url = plgn.get("download_url", "")
                plugin_info.status = "available"  # "unknown"
                plugin_info.date_added = plgn.get("date_added", None)
            self.plugins.repo_cache[plugin_info.guid] = plugin_info
