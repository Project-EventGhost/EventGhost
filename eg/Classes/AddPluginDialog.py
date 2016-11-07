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

import wx

# Local imports
import eg

KIND_TAGS = ["other", "remote", "program", "external"]

class Config(eg.PersistentData):
    position = None
    size = (640, 450)
    splitPosition = 240
    lastSelection = None
    collapsed = set()
    lastSelectionRepo = None
    collapsedRepo = set()


class Text(eg.TranslatableStrings):
    title = "Add Plugin..."
    noInfo = "No information available."
    noMultiloadTitle = "No multiload possible"
    noMultiload = (
        "This plugin doesn't support multiload and you already have one "
        "instance of this plugin in your configuration."
    )
    otherPlugins = "General Plugins"
    remotePlugins = "Input Devices"
    programPlugins = "Software Control"
    externalPlugins = "Hardware Control"
    author = "Author:"
    uninstallPlugin = "Uninstall plugin"
    upgradePlugin = "Upgrade plugin"
    version = "Version:"
    versionAvailable = "Available version:"
    versionInstalled = "Installed version:"
    descriptionBox = "Description"


class AddPluginDialog(eg.TaskletDialog):
    instance = None

    def CheckMultiload(self):
        if not self.checkMultiLoad:
            return True
        info = self.resultData
        if not info:
            return True
        if info.canMultiLoad:
            return True
        if any((plugin.info.path == info.path) for plugin in eg.pluginList):
            eg.MessageBox(
                Text.noMultiload,
                Text.noMultiloadTitle,
                style=wx.ICON_EXCLAMATION
            )
            return False
        else:
            return True

    @eg.LogItWithReturn
    def Configure(self, parent, checkMultiLoad=True, title=None):
        if title is None:
            title = Text.title
        self.checkMultiLoad = checkMultiLoad
        if self.__class__.instance:
            self.__class__.instance.Raise()
            return
        self.__class__.instance = self

        self.resultData = None

        eg.TaskletDialog.__init__(
            self, parent, wx.ID_ANY, title,
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )

        self.imageList = imageList = wx.ImageList(16, 16)
        imageList.Add(eg.Icons.PLUGIN_ICON.GetBitmap())
        imageList.Add(eg.Icons.FOLDER_ICON.GetBitmap())


        splitterWindow = self.CreateUI()
        self.treeCtrl.Bind(wx.EVT_TREE_ITEM_RIGHT_CLICK, self.OnItemRightClick)
        self.Bind(wx.EVT_TREE_SEL_CHANGED, self.OnSelectionChanged)
        self.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.OnItemActivated)
        self.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.OnPageChange)

        self.UpdateLists()
        self.treeCtrl.SetFocus()

        while self.Affirmed():
            if self.CheckMultiload():
                self.SetResult(self.resultData)
        self.treeCtrl.Unbind(wx.EVT_TREE_SEL_CHANGED)
        self.treeCtrlRepo.Unbind(wx.EVT_TREE_SEL_CHANGED)
        Config.size = self.GetSizeTuple()
        Config.position = self.GetPositionTuple()
        Config.splitPosition = splitterWindow.GetSashPosition()
        Config.collapsed = set(
            kind for kind, treeId in self.typeIds.iteritems()
            if not self.treeCtrl.IsExpanded(treeId)
        )
        Config.collapsedRepo = set(
            kind for kind, treeId in self.typeIdsRepo.iteritems()
            if not self.treeCtrlRepo.IsExpanded(treeId)
        )
        self.__class__.instance = None

    def CreateUI(self):
        splitterWindow = wx.SplitterWindow(
            self,
            style=(
                wx.SP_LIVE_UPDATE |
                wx.CLIP_CHILDREN |
                wx.NO_FULL_REPAINT_ON_RESIZE
            )
        )

        self.notebook = notebook = wx.Notebook(splitterWindow)
        self.treeCtrl = wx.TreeCtrl(
            notebook,
            style=(
                wx.TR_SINGLE |
                wx.TR_HAS_BUTTONS |
                wx.TR_HIDE_ROOT |
                wx.TR_LINES_AT_ROOT
            )
        )
        self.treeCtrl.SetMinSize((170, 200))
        notebook.AddPage(self.treeCtrl, "local")

        self.treeCtrlRepo = wx.TreeCtrl(
            notebook,
            style=(
                wx.TR_SINGLE |
                wx.TR_HAS_BUTTONS |
                wx.TR_HIDE_ROOT |
                wx.TR_LINES_AT_ROOT
            )
        )
        self.treeCtrlRepo.SetMinSize((170, 200))
        notebook.AddPage(self.treeCtrlRepo, "online")

        rightPanel = wx.Panel(splitterWindow)
        rightSizer = wx.BoxSizer(wx.VERTICAL)
        rightPanel.SetSizer(rightSizer)

        self.nameText = nameText = wx.StaticText(rightPanel)
        nameText.SetFont(wx.Font(14, wx.SWISS, wx.NORMAL, wx.FONTWEIGHT_BOLD))
        rightSizer.Add(nameText, 0, wx.EXPAND | wx.LEFT | wx.BOTTOM, 5)

        subSizer = wx.FlexGridSizer(3, 2)
        self.authorLabel = wx.StaticText(rightPanel, label=Text.author)
        subSizer.Add(self.authorLabel)
        self.authorText = wx.StaticText(rightPanel)
        subSizer.Add(self.authorText, 0, wx.EXPAND | wx.LEFT, 5)
        self.versionLabel = wx.StaticText(rightPanel, label=Text.version)
        subSizer.Add(self.versionLabel)
        self.versionText = wx.StaticText(rightPanel)
        subSizer.Add(self.versionText, 0, wx.EXPAND | wx.LEFT, 5)
        self.versionAvailableLabel = wx.StaticText(
            rightPanel, label=Text.versionAvailable)
        subSizer.Add(self.versionAvailableLabel)
        self.versionAvailableText = wx.StaticText(rightPanel)
        subSizer.Add(self.versionAvailableText, 0, wx.EXPAND | wx.LEFT, 5)
        rightSizer.Add(subSizer, 0, wx.EXPAND | wx.LEFT | wx.BOTTOM, 5)

        staticBoxSizer = wx.StaticBoxSizer(
            wx.StaticBox(rightPanel, label=Text.descriptionBox)
        )

        self.descrBox = eg.HtmlWindow(rightPanel)
        staticBoxSizer.Add(self.descrBox, 1, wx.EXPAND)

        rightSizer.Add(staticBoxSizer, 1, wx.EXPAND | wx.LEFT, 5)

        splitterWindow.SplitVertically(notebook, rightPanel)
        splitterWindow.SetMinimumPaneSize(60)
        splitterWindow.SetSashGravity(0.0)
        splitterWindow.UpdateSize()

        self.buttonRow = eg.ButtonRow(self, (wx.ID_OK, wx.ID_CANCEL), True)
        self.okButton = self.buttonRow.okButton
        self.okButton.Enable(False)

        mainSizer = wx.BoxSizer(wx.VERTICAL)
        mainSizer.Add(splitterWindow, 1, wx.EXPAND | wx.ALL, 5)
        mainSizer.Add(self.buttonRow.sizer, 0, wx.EXPAND)

        self.SetSizerAndFit(mainSizer)
        self.SetSize(Config.size)
        splitterWindow.SetSashPosition(Config.splitPosition)
        if Config.position:
            self.SetPosition(Config.position)
        return splitterWindow

    def InitTreeCtrl(self, plugins, treeCtrl, lastSelection, collapsed):
        imageList = self.imageList
        treeCtrl.SetImageList(imageList)

        root = treeCtrl.AddRoot("")
        typeIds = {
            KIND_TAGS[0]: treeCtrl.AppendItem(
                root, getattr(Text, KIND_TAGS[0] + "Plugins"), 1
            ),
            KIND_TAGS[1]: treeCtrl.AppendItem(
                root, getattr(Text, KIND_TAGS[1] + "Plugins"), 1
            ),
            KIND_TAGS[2]: treeCtrl.AppendItem(
                root, getattr(Text, KIND_TAGS[2] + "Plugins"), 1
            ),
            KIND_TAGS[3]: treeCtrl.AppendItem(
                root, getattr(Text, KIND_TAGS[3] + "Plugins"), 1
            ),
        }

        itemToSelect = None
        for info in plugins:
            if info.kind in ("hidden", "core"):
                continue
            if info.icon and info.icon != eg.Icons.PLUGIN_ICON:
                try:
                    idx = imageList.Add(
                        eg.Icons.PluginSubIcon(info.icon).GetBitmap()
                    )
                except BaseException:
                    idx = 0
            else:
                idx = 0

            class colours:
                Deprecated_Bg = wx.Colour(238, 187, 204)
                Deprecated_Tx = wx.Colour(102, 0, 0)
                Error_Bg = wx.Colour(255, 255, 136)
                Error_Tx = wx.Colour(204, 0, 0)
                Experimental_Bg = wx.Colour(238, 238, 187)
                Experimental_Tx = wx.Colour(102, 0, 0)
                New_Bg = wx.Colour(204, 255, 204)
                New_Tx = wx.Colour(0, 136, 0)
                Newer_Bg = wx.Colour(255, 255, 205)
                Newer_Tx = wx.Colour(85, 0, 0)
                Upgradeable_Bg = wx.Colour(255, 255, 170)
                Upgradeable_Tx = wx.Colour(136, 0, 0)

            treeId = treeCtrl.AppendItem(typeIds[info.kind], info.name, idx)
            if info.status in ["orphan", "broken", "unknown"]:
                treeCtrl.SetItemBackgroundColour(treeId, colours.Error_Bg)
                treeCtrl.SetItemTextColour(treeId, colours.Error_Tx)
                treeCtrl.SetItemBold(treeId)
            elif info.status == "newer":
                treeCtrl.SetItemBackgroundColour(treeId, colours.Newer_Bg)
                treeCtrl.SetItemTextColour(treeId, colours.Newer_Tx)
                treeCtrl.SetItemBold(treeId)
            elif info.status == "upgradeable":
                treeCtrl.SetItemBackgroundColour(treeId, colours.Upgradeable_Bg)
                treeCtrl.SetItemTextColour(treeId, colours.Upgradeable_Tx)
                treeCtrl.SetItemBold(treeId)
            elif info.status == "new":
                treeCtrl.SetItemBackgroundColour(treeId, colours.New_Bg)
                treeCtrl.SetItemTextColour(treeId, colours.New_Tx)
                treeCtrl.SetItemBold(treeId)

            treeCtrl.SetPyData(treeId, info)
            if info.path == lastSelection:
                itemToSelect = treeId

        for kind, treeId in typeIds.iteritems():
            if kind in collapsed:
                treeCtrl.Collapse(treeId)
            else:
                treeCtrl.Expand(treeId)

        if not itemToSelect:
            for kind in KIND_TAGS:
                itemToSelect, _ = treeCtrl.GetFirstChild(typeIds[kind])
                if itemToSelect.IsOk():
                    break
            else:
                itemToSelect = None

        if itemToSelect:
            treeCtrl.ScrollTo(itemToSelect)
            treeCtrl.SelectItem(itemToSelect)

        return typeIds

    def SetupContextMenu(self, info):
        menu = wx.Menu()
        menuItem = menu.Append(wx.ID_ANY, eg.text.MainFrame.Menu.Export)
        menu.Bind(wx.EVT_MENU, self.OnExport, id=menuItem.GetId())
        menuItem = menu.Append(wx.ID_ANY, Text.uninstallPlugin)
        menu.Bind(wx.EVT_MENU, self.OnUninstall, id=menuItem.GetId())
        if info.status == "upgradeable":
            menuItem = menu.Append(wx.ID_ANY, Text.upgradePlugin)
            menu.Bind(wx.EVT_MENU, self.OnUpgrade, id=menuItem.GetId())

        return menu

    def OnExport(self, dummyEvent=None):
        info = self.treeCtrl.GetPyData(self.treeCtrl.GetSelection())
        if info:
            eg.PluginInstall.Export(info)

    def OnPageChange(self, event):
        treeCtrl = self.notebook.GetCurrentPage()
        item = treeCtrl.GetSelection()
        self.UpdateDetailsSection(item, treeCtrl)
        wx.CallAfter(treeCtrl.SetFocus)

    def OnItemActivated(self, event):
        treeCtrl = self.notebook.GetCurrentPage()
        item = treeCtrl.GetSelection()
        info = treeCtrl.GetPyData(item)
        if info is not None:
            self.OnOK(wx.CommandEvent())
            return
        event.Skip()

    def OnItemRightClick(self, event):
        """
        Handles wx.EVT_TREE_ITEM_RIGHT_CLICK events.
        """
        item = event.GetItem()
        self.treeCtrl.SelectItem(item)
        info = self.treeCtrl.GetPyData(item)
        if info:
            self.PopupMenu(self.SetupContextMenu(info))

    def OnSelectionChanged(self, event):
        """
        Handle the wx.EVT_TREE_SEL_CHANGED events.
        """
        treeCtrl = event.GetEventObject()
        page = self.notebook.GetCurrentPage()
        if page != treeCtrl:
            return
        item = event.GetItem()
        self.UpdateDetailsSection(item, treeCtrl)

    def OnUninstall(self, event):
        info = self.treeCtrl.GetPyData(self.treeCtrl.GetSelection())
        if not info:
            return
        eg.pluginManager.UninstallPlugin(info.guid)
        self.UpdateLists()

    def OnUpgrade(self, event):
        info = self.treeCtrl.GetPyData(self.treeCtrl.GetSelection())
        if not info:
            return
        eg.pluginManager.UpgradePlugin(info.guid)
        self.UpdateLists()

    def UpdateLists(self):
        self.treeCtrl.Freeze()
        self.treeCtrlRepo.Freeze()
        self.treeCtrl.DeleteAllItems()
        self.treeCtrlRepo.DeleteAllItems()
        if not eg.pluginManager.fetched_in_session:
            eg.pluginManager.repository.DoFetching()
        self.typeIds = self.InitTreeCtrl(
            eg.pluginManager.GetInstalledInfoList(), self.treeCtrl,
            Config.lastSelection, Config.collapsed
        )
        self.typeIdsRepo = self.InitTreeCtrl(
            eg.pluginManager.GetAvailableInfoList(), self.treeCtrlRepo,
            Config.lastSelectionRepo, Config.collapsedRepo
        )
        self.treeCtrl.Thaw()
        self.treeCtrlRepo.Thaw()

    def UpdateDetailsSection(self, item, treeCtrl):
        if not item.IsOk():
            return
        self.resultData = info = treeCtrl.GetPyData(item)
        if info is None:
            name = treeCtrl.GetItemText(item)
            description = Text.noInfo
            self.authorLabel.SetLabel("")
            self.authorText.SetLabel("")
            self.versionLabel.SetLabel("")
            self.versionText.SetLabel("")
            self.versionAvailableLabel.SetLabel("")
            self.versionAvailableText.SetLabel("")
            self.okButton.Enable(False)
        else:
            name = info.name
            description = info.description
            self.descrBox.SetBasePath(info.path)
            self.authorLabel.SetLabel(Text.author)
            self.authorText.SetLabel(info.author.replace("&", "&&"))


            self.okButton.Enable(True)
            if treeCtrl == self.treeCtrl:
                Config.lastSelection = info.path
                self.versionLabel.SetLabel(Text.version)
                self.versionText.SetLabel(info.version)
                if info.status == "upgradeable":
                    self.versionAvailableLabel.SetLabel(Text.versionAvailable)
                    self.versionAvailableText.SetLabel(info.versionAvailable)
                else:
                    self.versionAvailableLabel.SetLabel("")
                    self.versionAvailableText.SetLabel("")
            else:
                Config.lastSelectionRepo = info.path
                self.versionAvailableLabel.SetLabel(Text.versionAvailable)
                self.versionAvailableText.SetLabel(info.versionAvailable)
                if info.status == "upgradeable":
                    self.versionLabel.SetLabel(Text.versionInstalled)
                    self.versionText.SetLabel(info.version)
                else:
                    self.versionLabel.SetLabel("")
                    self.versionText.SetLabel("")
        self.nameText.SetLabel(name)
        url = info.url if info else None
        self.descrBox.SetPage(eg.Utils.AppUrl(description, url))

