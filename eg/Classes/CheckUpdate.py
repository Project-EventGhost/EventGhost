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

import threading
import webbrowser
import wx
from agithub.GitHub import GitHub
from pkg_resources import parse_version

# Local imports
import eg


class Text(eg.TranslatableStrings):
    newVersionMesg = \
        "A new version of EventGhost has been released!\n\n"\
        "Your version:\t%s\n"\
        "Newest version:\t%s\n\n"\
        "Do you want to visit the download page now?"
    waitMesg = "Please wait while EventGhost retrieves update information."
    ManOkMesg = "There is currently no newer version of EventGhost available."
    ManErrorMesg = \
        "It wasn't possible to get the information from the EventGhost "\
        "website.\n\n"\
        "Please try it again later."
    wipUpdateMsg = "Update check not available when running from source."


class CheckUpdate(object):
    def __init__(self):
        self.timerEG = UpdateCheckTimer(
            "CheckUpdateEG", _checkUpdateMainProg
        )
        self.timerPlugins = UpdateCheckTimer(
            "CheckUpdatePlugins", eg.pluginManager.UpdateCheck
        )

        if eg.config.checkUpdateEGOnStart:
            self.RequestCheck(
                "lastUpdateCheckDateEG",
                "CheckUpdateEG",
                _checkUpdateMainProg
            )

        if eg.config.checkUpdatePluginOnStart:
            self.RequestCheck(
                "lastUpdateCheckDatePlugins",
                "CheckUpdatePlugins",
                eg.pluginManager.UpdateCheck
            )

        if eg.config.checkUpdateEGContinuous:
            self.StartContinuous("EG")

        if eg.config.checkUpdatePluginContinuous:
            self.StartContinuous("Plugins")

    @eg.LogIt
    def RequestCheck(self, attr, name, func):
        today = wx.DateTime_Today()
        last = wx.DateTime()
        try:
            last.ParseISODate(getattr(eg.config, attr))
        except TypeError:
            pass
        # avoid more than one check per day
        if last != today:
            setattr(eg.config, attr, today.FormatISODate())
            wx.CallAfter(
                self.CheckerThread,
                func,
                name
            )

    @eg.LogIt
    def StartContinuous(self, attr):
        # millisecond * second * minute * hour * day
        ms = 1000 * 1 * 60 * 60 * 24
        getattr(self, "timer" + attr).Start(ms, oneShot=wx.TIMER_CONTINUOUS)

    @eg.LogIt
    def StopContinuous(self, attr):
        getattr(self, "timer"+attr).Stop()

    @staticmethod
    def CheckerThread(func, name):
        threading.Thread(
            target=func,
            name=name
        ).start()

    @staticmethod
    def EGManually():
        _checkUpdateMainProg(manually=True)

    @staticmethod
    def PluginsManually():
        eg.pluginManager.UpdateCheck(manually=True)


class MessageDialog(eg.Dialog):
    def __init__(self, version, url):
        self.url = url
        eg.Dialog.__init__(self, None, -1, eg.APP_NAME)
        bmp = wx.ArtProvider.GetBitmap(
            wx.ART_INFORMATION,
            wx.ART_MESSAGE_BOX,
            (32, 32)
        )
        staticBitmap = wx.StaticBitmap(self, -1, bmp)
        staticText = self.StaticText(
            Text.newVersionMesg % (eg.Version.string, version)
        )
        downloadButton = wx.Button(self, -1, eg.text.General.ok)
        downloadButton.Bind(wx.EVT_BUTTON, self.OnOk)
        cancelButton = wx.Button(self, -1, eg.text.General.cancel)
        cancelButton.Bind(wx.EVT_BUTTON, self.OnCancel)

        sizer2 = eg.HBoxSizer(
            (staticBitmap, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 10),
            ((5, 5), 0),
            (
                staticText,
                0,
                wx.TOP | wx.RIGHT | wx.BOTTOM | wx.ALIGN_CENTER_VERTICAL,
                10
            ),
        )
        self.SetSizerAndFit(
            eg.VBoxSizer(
                (sizer2),
                ((5, 5), 1),
                (
                    eg.HBoxSizer(
                        (downloadButton),
                        ((5, 5), 0),
                        (cancelButton),
                    ), 0, wx.ALIGN_CENTER_HORIZONTAL
                ),
                ((2, 10), 0),
            )
        )
        self.ShowModal()

    def OnCancel(self, event):
        self.Close()

    def OnOk(self, event):
        webbrowser.open(self.url, True, True)
        self.Close()


class UpdateCheckTimer(wx.Timer):
    def __init__(self, attr, func, *args, **kwargs):
        super(UpdateCheckTimer, self).__init__(*args, **kwargs)
        self.attrInterval = "lastUpdateCheckDate" + attr[11:]
        self.func = func
        self.targetName = attr

    @eg.LogIt
    def Notify(self, *args, **kwargs):
        today = wx.DateTime_Today()
        last = wx.DateTime()
        try:
            last.ParseISODate(getattr(eg.config, self.attrInterval))
        except TypeError:
            last = today
        if today - last >= wx.TimeSpan_Days(getattr(eg.config, self.attrInterval)):
            setattr(eg.config, self.attrInterval, today.FormatISODate())
            eg.checkUpdate.CheckerThread(self.func, self.targetName)


def CenterOnParent(self):
    parent = eg.document.frame
    if parent is None:
        return
    x, y = parent.GetPosition()
    parentWidth, parentHeight = parent.GetSize()
    width, height = self.GetSize()
    self.SetPosition(
        ((parentWidth - width) / 2 + x, (parentHeight - height) / 2 + y)
    )


def ShowWaitDialog():
    dialog = wx.Dialog(None, style=wx.THICK_FRAME | wx.DIALOG_NO_PARENT)
    staticText = wx.StaticText(dialog, -1, Text.waitMesg)
    sizer = wx.BoxSizer(wx.HORIZONTAL)
    sizer.Add(staticText, 1, wx.ALL, 20)
    dialog.SetSizerAndFit(sizer)
    CenterOnParent(dialog)
    dialog.Show()
    wx.GetApp().Yield()
    return dialog


@eg.LogIt
def _checkUpdateMainProg(manually=False):
    if eg.Version.string == "WIP":
        if manually:
            wx.MessageBox(Text.wipUpdateMsg, eg.APP_NAME)
        return

    dialog = None
    try:
        if manually:
            dialog = ShowWaitDialog()

        gh = GitHub()

        rc, data = gh.repos["EventGhost"]["EventGhost"].releases.get()
        if rc == 200:
            for rel in data:
                if rel["prerelease"]:
                    if eg.config.checkPreRelease or "-" in eg.Version.string:
                        break
                else:
                    break

        if dialog:
            dialog.Destroy()
            dialog = None

        ver = rel["name"].lstrip("v")
        url = rel["html_url"]

        if (
            rc == 200 and
            parse_version(ver) > parse_version(eg.Version.string) and
            (manually or ver != eg.config.lastUpdateCheckVersion)
        ):
            eg.config.lastUpdateCheckVersion = ver
            wx.CallAfter(MessageDialog, ver, url)
        else:
            if manually:
                dlg = wx.MessageDialog(
                    None,
                    Text.ManOkMesg,
                    eg.APP_NAME,
                    style=wx.OK | wx.ICON_INFORMATION
                )
                dlg.ShowModal()
                dlg.Destroy()
    except:
        if dialog:
            dialog.Destroy()
        if manually:
            dlg = wx.MessageDialog(
                None,
                Text.ManErrorMesg,
                eg.APP_NAME,
                style=wx.OK | wx.ICON_ERROR
            )
            dlg.ShowModal()
            dlg.Destroy()
