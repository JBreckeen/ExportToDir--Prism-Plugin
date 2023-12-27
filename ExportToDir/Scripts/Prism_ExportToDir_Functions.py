# -*- coding: utf-8 -*-
#
####################################################
#
# PRISM - Pipeline for animation and VFX projects
#
# www.prism-pipeline.com
#
# contact: contact@prism-pipeline.com
#
####################################################
#
#
# Copyright (C) 2016-2021 Richard Frangenberg
#
# Licensed under GNU LGPL-3.0-or-later
#
# This file is part of Prism.
#
# Prism is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Prism is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with Prism.  If not, see <https://www.gnu.org/licenses/>.
####################################################


try:
    from PySide2.QtCore import *
    from PySide2.QtGui import *
    from PySide2.QtWidgets import *
    from PySide2.QtCore import QObject, Signal

except:
    from PySide.QtCore import *
    from PySide.QtGui import *

from PrismUtils.Decorators import err_catcher_plugin as err_catcher

import os                                           #   CLEANUP     TODO
import shutil
import re
import subprocess
import threading
import zipfile
import tempfile
import json
import ntpath
from functools import partial         # NEEDED ???

from ExportToDir import ExportToDir

PROG_GREEN = "QProgressBar::chunk { background-color: rgb(0, 150, 0); }"
PROG_BLUE = "QProgressBar::chunk { background-color: rgb(0, 131, 195); }"
PROG_RED = "QProgressBar::chunk { background-color: rgb(225, 0, 0); }"


class Prism_ExportToDir_Functions(object):
    def __init__(self, core, plugin):
        self.core = core
        self.plugin = plugin

        self.loadedPlugins = []

        self.singleFileMode = True

        self.menuContext = ""
        self.saveDirs = ""
        self.outputPath = ""

        #   Global Settings File
        global settingsFile
        pluginLocation = os.path.dirname(os.path.dirname(__file__))
        settingsFile = os.path.join(pluginLocation, "ExportToDir_Config.json")

        #   Callbacks
        #   TODO    Doesn't seem to be a callback for the Project Chooser
        self.core.registerCallback("projectBrowserContextMenuRequested", self.projectBrowserContextMenuRequested, plugin=self)      

        self.core.registerCallback("openPBFileContextMenu", self.openPBFileContextMenu, plugin=self)   
        self.core.registerCallback("productSelectorContextMenuRequested", self.productSelectorContextMenuRequested, plugin=self)        
        self.core.registerCallback("mediaPlayerContextMenuRequested", self.mediaPlayerContextMenuRequested, plugin=self)        
        self.core.registerCallback("textureLibraryTextureContextMenuRequested", self.textureLibraryTextureContextMenuRequested, plugin=self)
        self.core.registerCallback("userSettings_loadUI", self.userSettings_loadUI, plugin=self)
        self.core.registerCallback("onUserSettingsSave", self.onUserSettingsSave, plugin=self)


    # if returns true, the plugin will be loaded by Prism
    @err_catcher(name=__name__)
    def isActive(self):
        return True
    
    #   Called with Callback - User Settings
    @err_catcher(name=__name__)
    def onUserSettingsSave(self, origin):

        self.saveSettings()

    #   Called with Callback - Project Browser
    @err_catcher(name=__name__)                                                     #   TODO
    def projectBrowserContextMenuRequested(self, origin, menu):


        pass


    #   Called with Callback - SceneFiles Browser
    @err_catcher(name=__name__)
    def openPBFileContextMenu(self, origin, rcmenu, filePath):

        self.menuContext = "Scene Files:"
        self.singleFileMode = True


        #   Retrieves File Info from Core
        fileData = self.core.getScenefileData(filePath)
        fileData["sourceDir"], fileData["sourceFilename"] = ntpath.split(fileData["filename"])
        fileData["sourcePath"] = fileData["filename"]
        #   Retrieves File Info from Project Config
        pData = self.core.getConfig(config="project", dft=3)        
        fileData["project_name"] = pData["globals"]["project_name"]
        #   Sends File Info to get sorted
        self.loadCoreData(fileData)
        #   Adds Right Click Item
        if os.path.isfile(fileData["filename"]):
            sendToAct = QAction("Export to Dir...", rcmenu)
            sendToAct.triggered.connect(lambda: self.sendToDialogue())
            rcmenu.addAction(sendToAct)


    #   Called with Callback - Product Browser
    @err_catcher(name=__name__)
    def productSelectorContextMenuRequested(self, origin, viewUi, pos, rcmenu):

        version = origin.getCurrentVersion()
        if not version:
            return
                                                                                        #   Look at ProductBrowser line 922
        self.menuContext = "Product Files:"
        self.singleFileMode = True

        #   Gets Source Path from Last Column
        row = viewUi.rowAt(pos.y())
        numCols = viewUi.columnCount()
        if row >= 0:
            sourcePath = viewUi.item(row, numCols - 1).text()

        infoFolder = self.core.products.getVersionInfoPathFromProductFilepath(sourcePath)
        infoPath = self.core.getVersioninfoPath(infoFolder)
        fileData = self.core.getConfig(configPath=infoPath)

        fileData["sourcePath"] = sourcePath
        fileData["sourceDir"], fileData["sourceFilename"] = ntpath.split(sourcePath)
        fileData["extension"] = os.path.splitext(fileData["sourceFilename"])[1]

        #   Adds Right Click Item
        if os.path.exists(sourcePath):
            sendToAct = QAction("Export to Dir...", viewUi)
            sendToAct.triggered.connect(lambda: self.sendToDialogue())
            rcmenu.addAction(sendToAct)

        #   Sends File Info to get sorted
        self.loadCoreData(fileData)


    #   Called with Callback - Media Browser
    @err_catcher(name=__name__)
    def mediaPlayerContextMenuRequested(self, origin, menu):

        if not type(origin.origin).__name__ == "MediaBrowser":
            return

        version = origin.origin.getCurrentVersion()
        if not version:
            return 

        self.menuContext = "Media Files:"

        if not origin.seq:
            return
        
        rawData = origin.getSelectedContexts()

        if rawData and isinstance(rawData[0], dict):
            fileData = rawData[0]
        else:
            fileData = {}

        fileData["sourceDir"] = fileData["path"]
        fileData["extension"] = os.path.splitext(fileData["source"])[1]

        if len(origin.seq) < 2:
            self.singleFileMode = True
            fileData["sourcePath"] = origin.seq[0]
            fileData["sourceFilename"] = os.path.basename(origin.seq[0])

        elif len(origin.seq) > 1:
            self.singleFileMode = False
            fileData["currentFrame"] = origin.seq[origin.getCurrentFrame()]
            fileData["sourceFilename"] = fileData["source"]

            fileList = []
            for file in origin.seq:
                fileList.append(file)
            fileData["sourcePath"] = fileList

        self.loadCoreData(fileData)        


        sendToAct = QAction("Export to Dir...", self.core.pb.mediaBrowser)
        sendToAct.triggered.connect(lambda: self.sendToDialogue())
        menu.addAction(sendToAct)


    #   Called with Callback - Library Browser
    @err_catcher(name=__name__)                                             #   TODO Handle Tex Groups
    def textureLibraryTextureContextMenuRequested(self, origin, menu):

        if not type(origin).__name__ == "TextureWidget":
            return
        
        self.menuContext = "Library Files:"

        self.singleFileMode = True

        # print("\nSTART\n")
        # print(dir(origin))                                             #   TESTING

        # print(f"origin.objectName():  {origin.objectName()}")          #   THIS RETURNS "texture"
        # print(f"origin.path:  {origin.path}")
        # print(f"origin.paths:  {origin.paths}")                        #    RETURNS NONE
        # print(f"stackUnder:  {origin.stackUnder()}")                        #    RETURNS NONE

        # print("\nSTART\n")

        # print("\nSTART\n")
        # self.core.updateEnvironment()
        # filepath = self.core.getCurrentFileName()
        # print(f"getScenefileData:  {self.core.getScenefileData(filepath)}")
        # print("\nEND\n")


        sourcePath = origin.path
        sourceDir = os.path.dirname(sourcePath)
        sourceBasename = os.path.basename(sourcePath)
        sourceFilename, sourceExt = os.path.splitext(sourceBasename)

        fileData = {}

        pData = self.core.getConfig(config="project", dft=3)        
        fileData["project_name"] = pData["globals"]["project_name"]

        fileData["sourcePath"] = sourcePath
        fileData["sourceDir"] = sourceDir
        fileData["sourceFilename"] = sourceFilename
        fileData["extension"] = sourceExt

        self.loadCoreData(fileData)        
            
        if os.path.isfile(fileData["sourcePath"]):
            sendToAct = QAction("Export to Dir...", self.core.pb.mediaBrowser)
            sendToAct.triggered.connect(lambda: self.sendToDialogue())
            menu.addAction(sendToAct)


    #   Called with Callback
    @err_catcher(name=__name__)                                                         #   TODO MAKE ERROR CEHCKING
    def userSettings_loadUI(self, origin):  # ADDING "Export to Dir" TO SETTINGS

        # Loads Settings File
        namingSchemeData, exportToList = self.loadSettings()

        self.getLoadedPlugins()

        # Create a Widget
        origin.w_exportTo = QWidget()
        origin.lo_exportTo = QVBoxLayout(origin.w_exportTo)

        # Add a new box for "File Naming Scheme" before "Export to Dir"
        gb_fileNamingScheme = QGroupBox("File Naming Scheme")
        lo_fileNamingScheme = QVBoxLayout()

        #   Template for Tooltips
        templates = {
            "@PROJECT@": ["Scene", "Product", "Media", "Library"],
            "@USER@": ["Scene", "Product", "Media"],
            "@TYPE@": ["Scene", "Product", "Media"],
            "@SEQUENCE@": ["Scene", "Product", "Media"],
            "@SHOT@": ["Scene", "Product", "Media"],
            "@ASSET@": ["Scene", "Product", "Media"],
            "@DEPARTMENT@": ["Scene", "Product", "Media"],
            "@TASK@": ["Scene", "Product", "Media"],
            "@FILENAME@": ["Scene", "Product", "Media", "Library"],
            "@VERSION@": ["Scene", "Product", "Media", "Library"],
            "@FILETYPE@": ["Scene", "Product", "Media"],
            "@EXTENSION@": ["Scene", "Product", "Media", "Library"],
            "@PRODUCT@": ["Product"],
            "@AOV@": ["Media"],
            "@CHANNEL@": ["Media"],
            "@IDENTIFIER@": ["Media"]
            }

        # Add Text Boxes
        self.l_naming_SceneFiles = QLabel("Scene Files:")
        self.e_naming_SceneFiles = QLineEdit()
        sceneFileTip = self.getToolTipItems(templates, "Scene")
        self.e_naming_SceneFiles.setToolTip(sceneFileTip)

        self.l_naming_ProductFiles = QLabel("Product Files:")
        self.e_naming_ProductFiles = QLineEdit()
        productFileTip = self.getToolTipItems(templates, "Product")
        self.e_naming_ProductFiles.setToolTip(productFileTip)

        self.l_naming_MediaFiles = QLabel("Media Files:")
        self.e_naming_MediaFiles = QLineEdit()
        mediaFileTip = self.getToolTipItems(templates, "Media")
        self.e_naming_MediaFiles.setToolTip(mediaFileTip)        

        self.l_naming_LibraryFiles = QLabel("Library Files:")
        self.e_naming_LibraryFiles = QLineEdit()
        libraryFileTip = self.getToolTipItems(templates, "Library")
        self.e_naming_LibraryFiles.setToolTip(libraryFileTip)        

        # Add a grid layout
        lo_fileNamingScheme = QGridLayout()

        # Add each QLabel and QLineEdit to the layout with the same starting position
        lo_fileNamingScheme.addWidget(self.l_naming_SceneFiles, 0, 0)
        lo_fileNamingScheme.addWidget(self.e_naming_SceneFiles, 0, 1)

        lo_fileNamingScheme.addWidget(self.l_naming_ProductFiles, 1, 0)
        lo_fileNamingScheme.addWidget(self.e_naming_ProductFiles, 1, 1)

        lo_fileNamingScheme.addWidget(self.l_naming_MediaFiles, 2, 0)
        lo_fileNamingScheme.addWidget(self.e_naming_MediaFiles, 2, 1)

        if "Libraries" in self.loadedPlugins:
            lo_fileNamingScheme.addWidget(self.l_naming_LibraryFiles, 3, 0)
            lo_fileNamingScheme.addWidget(self.e_naming_LibraryFiles, 3, 1)

        # Set column stretch to make sure line edits are aligned
        lo_fileNamingScheme.setColumnStretch(1, 1)

        gb_fileNamingScheme.setLayout(lo_fileNamingScheme)

        # Add the "File Naming Scheme" box before the "Export to Dir" group box
        origin.lo_exportTo.addWidget(gb_fileNamingScheme)

        spacer = QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Fixed)
        origin.lo_exportTo.addItem(spacer)

        # Add the "Export to Dir" group box
        gb_exportTo = QGroupBox("User Export to Dir Locations")
        lo_exportTo = QVBoxLayout()
        gb_exportTo.setLayout(lo_exportTo)

        headerLabels = ["Name", "Path"]
        self.tw_exportTo = QTableWidget()
        self.tw_exportTo.setColumnCount(len(headerLabels))
        self.tw_exportTo.setHorizontalHeaderLabels(headerLabels)
        self.tw_exportTo.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tw_exportTo.horizontalHeader().setDefaultAlignment(Qt.AlignLeft)

        # Sets initial Table size
        self.tw_exportTo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Adds Buttons
        w_exportTo = QWidget()
        lo_exportToButtons = QHBoxLayout()
        b_addoexportTo = QPushButton("Add")
        b_removeoexportTo = QPushButton("Remove")

        w_exportTo.setLayout(lo_exportToButtons)
        lo_exportToButtons.addStretch()
        lo_exportToButtons.addWidget(b_addoexportTo)
        lo_exportToButtons.addWidget(b_removeoexportTo)

        lo_exportTo.addWidget(self.tw_exportTo)
        lo_exportTo.addWidget(w_exportTo)
        origin.lo_exportTo.addWidget(gb_exportTo)

        # Sets Columns
        self.tw_exportTo.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding))
        # Makes ReadOnly
        self.tw_exportTo.setEditTriggers(QAbstractItemView.NoEditTriggers)

        # Executes button actions
        b_addoexportTo.clicked.connect(lambda: self.addExportToDir(origin, self.tw_exportTo))
        b_removeoexportTo.clicked.connect(lambda: self.removeExportToDir(origin, self.tw_exportTo))

        # Populates lists from Settings File Data
        self.e_naming_SceneFiles.setText(namingSchemeData.get("Scene Files:", ""))
        self.e_naming_ProductFiles.setText(namingSchemeData.get("Product Files:", ""))
        self.e_naming_MediaFiles.setText(namingSchemeData.get("Media Files:", ""))
        self.e_naming_LibraryFiles.setText(namingSchemeData.get("Library Files:", ""))

        for item in exportToList:
            row_position = self.tw_exportTo.rowCount()
            self.tw_exportTo.insertRow(row_position)
            self.tw_exportTo.setItem(row_position, 0, QTableWidgetItem(item.get("Name", "")))
            self.tw_exportTo.setItem(row_position, 1, QTableWidgetItem(item.get("Path", "")))

        # Add Tab to User Settings
        origin.addTab(origin.w_exportTo, "Export to Dir")


    #   Set Settings Tooltips
    @err_catcher(name=__name__)
    def getToolTipItems(self, template, textbox):
        
        templateItems = "Available variables:\n\n"
        for key, value in template.items():
            if textbox in value:
                templateItems += key + "\n"

        return templateItems


    #   Check Loaded Plugins
    @err_catcher(name=__name__)
    def getLoadedPlugins(self):

        pluginNames = ["Standalone",
                       "Libraries",
                       "USD"
                       ]
        
        for plugin in pluginNames:
            pluginName = self.core.plugins.getPlugin(plugin)
            if pluginName is not None:
                self.loadedPlugins.append(plugin)

    #   Receives File Data and Populates Variables
    @err_catcher(name=__name__)
    def loadCoreData(self, fileData):

        print("\n\n")                                               #   TESTING
        try:
            print(f"fileData:  {fileData}")                         #   TESTING

            self.projectName = ""
            self.userName = ""
            self.entityType = ""
            self.sequenceName = ""
            self.shotName = ""
            self.assetName = ""
            self.deptName = ""
            self.taskName = ""
            self.productName = ""
            self.identifier = ""
            self.version = ""
            self.aov = ""
            self.channel = ""
            self.sourcePath = ""            
            self.sourceFilename = ""
            self.currentFrame = None
            self.sourceExt = ""

            if "project_name" in fileData:
                self.projectName = fileData["project_name"]
            if "user" in fileData:
                self.userName = fileData["user"]                    
            if "type" in fileData:
                self.entityType = fileData["type"]                  
            if "sequence" in fileData:
                self.sequenceName = fileData["sequence"]
            if "shot" in fileData:
                self.shotName = fileData["shot"]
            if "asset" in fileData:
                self.assetName = fileData["asset"]
            if "department" in fileData:
                self.deptName = fileData["department"]
            if "task" in fileData:
                self.taskName = fileData["task"]
            if "product" in fileData:
                self.productName = fileData["product"]                
            if "identifier" in fileData:
                self.identifier = fileData["identifier"]
            if "version" in fileData:
                self.version = fileData["version"]                        
            if "aov" in fileData:
                self.aov = fileData["aov"]
            if "channel" in fileData:
                self.channel = fileData["channel"]                
            if "sourcePath" in fileData:
                self.sourcePath = fileData["sourcePath"]                     
            if "sourceDir" in fileData:
                self.sourceDir = fileData["sourceDir"]                
            if "sourceFilename" in fileData:
                self.sourceFilename = fileData["sourceFilename"]
            if "currentFrame" in fileData:
                self.currentFrame = fileData["currentFrame"]
            if "extension" in fileData:
                self.sourceExt = fileData["extension"]



        except:
            print("Cannot show Data")                       #   TESTING
############  vvvvvvvvvvvvvvvvvvvvvvvvvvvv   ################################

        print("\n\n")                           #   TESTING
              
        attributes = ["projectName",
                      "userName",
                      "entityType",
                      "sequenceName",
                      "shotName",
                      "assetName",
                      "deptName",
                      "taskName",
                      "productName",
                      "identifier",
                      "version",
                      "aov",
                      "channel",
                      "sourcePath",
                      "sourceDir",
                      "sourceFilename",
                      "currentFrame",
                      "sourceExt"]

        for attribute in attributes:
            if hasattr(self, attribute):
                value = getattr(self, attribute)
                print(f"{attribute}: {value}")
############  ^^^^^^^^^^^^^^^^^^^^^^^^^^    ##############################

    #   Load Settings from Global Settings File
    @err_catcher(name=__name__)
    def loadSettings(self, context=None):
        try:
            with open(settingsFile, "r") as json_file:
                data = json.load(json_file)

                namingScheme = data.get("NamingScheme", {})
                exportPaths = data.get("ExportPaths", [])

                if context is None:
                    return namingScheme, exportPaths
                else:
                    template = namingScheme.get(context)
                    return template

        except FileNotFoundError:
            return {}, []


    #   Saves Settings to Global Settings File
    @err_catcher(name=__name__)
    def saveSettings(self):

        namingSchemeData = {}
        exportPathsData = []
        NameSchemes = ["SceneFiles",
                      "ProductFiles",
                      "MediaFiles",
                      "LibraryFiles"]

        # Populates naming scheme data from line edits
        for name in NameSchemes:
            label = getattr(self, f"l_naming_{name}")
            line_edit = getattr(self, f"e_naming_{name}")

            labelText = label.text()
            contents = line_edit.text()
            namingSchemeData[labelText] = contents

        # Populates export paths data from UI List
        for row in range(self.tw_exportTo.rowCount()):
            nameItem = self.tw_exportTo.item(row, 0)
            pathItem = self.tw_exportTo.item(row, 1)

            if nameItem and pathItem:
                name = nameItem.text()
                location = pathItem.text()
                exportPathsData.append({"Name": name, "Path": location})

        # Save both dictionaries
        with open(settingsFile, "w") as json_file:
            json.dump({"NamingScheme": namingSchemeData, "ExportPaths": exportPathsData}, json_file, indent=4)


    #   Adds Dir to ExportToDir User Settings GUI
    @err_catcher(name=__name__)
    def addExportToDir(self, origin, tw_exportTo):

        #   Calls Custon Dialog
        dialog = AddExportToDirDialog(origin)

        #   Adds Name and Path to UI List
        if dialog.exec_() == QDialog.Accepted:
            name, path = dialog.getValues()

            if name and path:
                row_position = tw_exportTo.rowCount()
                tw_exportTo.insertRow(row_position)
                tw_exportTo.setItem(row_position, 0, QTableWidgetItem(name))
                tw_exportTo.setItem(row_position, 1, QTableWidgetItem(path))

            #   Saves UI List to JSON file
            self.saveSettings()


    #   Removes Dir to ExportToDir User Settings GUI
    @err_catcher(name=__name__)
    def removeExportToDir(self, origin, tw_exportTo):

        selectedRow = tw_exportTo.currentRow()

        if selectedRow != -1:
            tw_exportTo.removeRow(selectedRow)

            #   Saves UI List to JSON file
            self.saveSettings()


    @err_catcher(name=__name__)
    def loadData(self, dlg):

        pData = self.core.getConfig(config="project", dft=3)
        self.loadSaveDirs(pData)

        dlg.e_customLoc.setText(self.sourceDir)


    @err_catcher(name=__name__)                         #   TODO ADD SETTINGS MENU FOLDERS
    def loadSaveDirs(self, pData):    

        projectPaths = set()
        self.saveDirs = []

        #   Loads Dirs from Project Render Locations
        if pData["render_paths"]:
            renderLocs = pData["render_paths"]

            for locName, locPath in renderLocs.items():
                if locPath not in projectPaths:
                    projectPaths.add(locPath)
                    self.saveDirs.append(locPath)

        #   Loads Dirs from Project Export Locations
        if pData["export_paths"]:
            exportLocs = pData["export_paths"]

            for locName, locPath in exportLocs.items():
                if locPath not in projectPaths:
                    projectPaths.add(locPath)
                    self.saveDirs.append(locPath)

        # Load Dirs from Export to Dir User Settings
        namingScheme, exportPaths = self.loadSettings()
        for item in exportPaths:
            path = item.get("Path")
            if path and path not in projectPaths:
                projectPaths.add(path)
                self.saveDirs.append(path)


    @err_catcher(name=__name__)
    def sendToDialogue(self):

        dlg = ExportToDir()
        dlg.setWindowTitle("Export to Directory")

        dlg.rb_singleImage.hide()
        dlg.rb_imageSeq.hide()
        dlg.rb_singleImage.setChecked(True)

        self.loadData(dlg)

        existingFolders = self.saveDirs
        dlg.cb_mediaFolders.addItems(existingFolders)

        dlg.rb_ProjectFolder.setChecked(True)

        self.setPlaceholderName(dlg, load=True)
        self.setSequenceMode(dlg)

        #   Connections
        dlg.e_mediaName.textEdited.connect(lambda: self.refreshOutputName(dlg))
        dlg.but_nameReset.clicked.connect(lambda: self.setPlaceholderName(dlg, load=True))
        dlg.butGroup_folder.buttonClicked.connect(lambda: self.refreshOutputName(dlg))
        dlg.butGroup_imageSeq.buttonClicked.connect(lambda: self.setSequenceMode(dlg))
        dlg.cb_mediaFolders.currentIndexChanged.connect(lambda: self.refreshOutputName(dlg))
        dlg.but_customPathSearch.clicked.connect(lambda: self.openExplorer(dlg, self.sourcePath, set=True))
        dlg.e_appendFolder.textEdited.connect(lambda: self.formatAppendFolder(dlg))
        dlg.chb_zipFile.clicked.connect(lambda: self.setSequenceMode(dlg))
        dlg.but_explorer.clicked.connect(lambda: self.openExplorer(dlg, self.outputPath))        
        dlg.buttonBox.button(QDialogButtonBox.Save).clicked.connect(lambda: self.execute(dlg))
        dlg.buttonBox.button(QDialogButtonBox.Close).clicked.connect(dlg.reject)        

        self.refreshOutputName(dlg)

        dlg.exec_()
    

    @err_catcher(name=__name__)
    def setSequenceMode(self, dlg):    

        if dlg.rb_singleImage.isChecked():
            self.singleFileMode = True
        else:
            self.singleFileMode = False

        if dlg.rb_imageSeq.isChecked() and not dlg.chb_zipFile.isChecked():
            dlg.e_mediaName.setReadOnly(True)
            dlg.e_mediaName.setStyleSheet("color: rgb(120, 120, 120);")
        else:
            dlg.e_mediaName.setReadOnly(False)
            dlg.e_mediaName.setStyleSheet("color: ;")

        self.setPlaceholderName(dlg)


    @err_catcher(name=__name__)
    def setPlaceholderName(self, dlg, load=False):

        if self.singleFileMode:
            if self.currentFrame:
                baseName = os.path.basename(self.currentFrame)           #   TODO
                fileNameNoExt = os.path.splitext(baseName)[0]
            else:
                fileNameNoExt = os.path.splitext(self.sourceFilename)[0]



#            if isinstance(self.sourceFilename, str):
#                fileNameNoExt, ext = os.path.splitext(self.sourceFilename)
#            else:
#                baseName = os.path.basename(self.sourcePath[self.sourceCurrentFrame])           #   TODO
#                fileNameNoExt, ext = os.path.splitext(baseName)

        else:
            dlg.rb_singleImage.show()
            dlg.rb_imageSeq.show()
            
            fileNameNoExt = os.path.splitext(self.sourceFilename)[0]  

#            match = re.search(r'\d+$', fileNameNoExt)
#            if match:
#                numeric_length = match.end() - match.start()
#                placeholder = '#' * numeric_length
#                fileNameNoExt = fileNameNoExt[:match.start()] + placeholder
            
        formattedNameNoExt = self.formatName(fileNameNoExt)
        formattedName = formattedNameNoExt + self.sourceExt

        template = self.loadSettings(context=self.menuContext)

        replacements = {
            "@PROJECT@": self.projectName,
            "@USER@": self.userName,
            "@TYPE@": self.entityType,
            "@SEQUENCE@": self.sequenceName,
            "@SHOT@": self.shotName,
            "@ASSET@": self.assetName,
            "@DEPARTMENT@": self.deptName,
            "@TASK@": self.taskName,
            "@PRODUCT@": self.productName,
            "@IDENTIFIER@": self.identifier,
            "@VERSION@": self.version,
            "@AOV@": self.aov,
            "@CHANNEL@": self.channel,
            "@FILENAME@": formattedName,
            "@FILETYPE@": self.sourceExt.removeprefix(".").upper(),
            "@EXTENSION@": self.sourceExt
        }

        # Perform replacements
        placeholderName = template  # Initialize with the original template
        for placeholder, value in replacements.items():
            placeholderName = placeholderName.replace(placeholder, value)


        dlg.e_mediaName.setText(placeholderName)

        if not load:
            self.refreshOutputName(dlg)




    def formatName(self, inputName):
        # Replace invalid characters with underscores
        validName = re.sub(r"[^a-zA-Z0-9_\- ()#.]", "_", inputName)

        # Check for reserved names for outputName
        reserved_names = set(['CON', 'PRN', 'AUX', 'NUL'] + [f'COM{i}' for i in range(1, 10)] + [f'LPT{i}' for i in range(1, 10)])
        if validName.upper() in reserved_names:
            self.core.popup("Name Not Allowed\n\nDo Not Use:\n\n   CON, PRN, AUX, NUL, COM, LPT")

        return validName


    @err_catcher(name=__name__)
    def formatAppendFolder(self, dlg):
        currentText = dlg.e_appendFolder.text()
        placeholderText = dlg.e_appendFolder.placeholderText()

        if currentText and currentText != placeholderText:
            # Check if the currentText needs a leading backslash
            if not currentText.startswith("\\"):
                currentText = "\\" + currentText

            # Call formatName without modifying e_appendFolder
            formatted_name = self.formatName(currentText[1:])

            # Check if formatted_name is not None before further processing
            if formatted_name is not None:
                # Update the e_appendFolder text with the formatted name
                dlg.e_appendFolder.setText("\\" + formatted_name)

            self.refreshOutputName(dlg)


    @err_catcher(name=__name__)                                     #   TODO RENAMING SEQ's
    def refreshOutputName(self, dlg):

        placeholderName = dlg.e_mediaName.text()
        root, extension = os.path.splitext(placeholderName)

        if extension:
            fileNameNoExt = root
        else:
            fileNameNoExt = placeholderName                                             
        
        formatedName = self.formatName(fileNameNoExt)
        
        if dlg.chb_zipFile.isChecked():
            if not self.singleFileMode:
                formatedName = formatedName.rstrip('#_.')
            formatedName = formatedName + ".zip"
        else:
            formatedName = fileNameNoExt + self.sourceExt

        if dlg.rb_ProjectFolder.isChecked():
            outputPath = dlg.cb_mediaFolders.currentText()

        elif dlg.rb_customFolder.isChecked():
            outputPath = dlg.e_customLoc.text()

        if dlg.e_appendFolder.text():
            appendFolder = dlg.e_appendFolder.text()

            if appendFolder.startswith("\\"):
                appendFolder = appendFolder[1:]

            AppendedOutputPath = os.path.normpath(os.path.join(outputPath, appendFolder))
            self.outputPath = os.path.normpath(os.path.join(AppendedOutputPath, formatedName))

        else:
            self.outputPath = os.path.join(outputPath, formatedName)

        dlg.e_outputName.setText(self.outputPath)

        self.resetProgBar(dlg)


    @err_catcher(name=__name__)
    def openExplorer(self, dlg, path, set=False):
 
        if dlg.rb_ProjectFolder.isChecked():
            path = dlg.cb_mediaFolders.currentText()

        elif dlg.rb_customFolder.isChecked():
            path = dlg.e_customLoc.text()
  
        path = path.replace("/", "\\")

        if set == True:
            customDir = QFileDialog.getExistingDirectory(None, "Select Save Directory", path)
            customDir = customDir.replace("/", "\\")
            dlg.e_customLoc.setText(customDir)
        else:
            cmd = "explorer " + path
            subprocess.Popen(cmd)

        self.refreshOutputName(dlg)


    @err_catcher(name=__name__)
    def resetProgBar(self, dlg):

        dlg.l_status.setText("Idle...")
        dlg.progressBar.reset()
        dlg.progressBar.setStyleSheet(PROG_BLUE)


    @err_catcher(name=__name__)
    def execute(self, dlg):

        self.resetProgBar(dlg)

        sourcePath = self.sourcePath
        outputName = dlg.e_mediaName.text()
        fileName, extension = os.path.splitext(outputName)

        if fileName == "":
            self.core.popup("The Output Filename is blank.  Please enter a Filename")
            return

        if isinstance(self.sourcePath, str) == False:
            if not dlg.rb_singleImage.isChecked() and not dlg.rb_imageSeq.isChecked():
                self.core.popup("Please Select Copy Type:\n\nSingle Image or Sequence")
                return
            elif dlg.rb_singleImage.isChecked():
                sourcePath = self.sourcePath[0]

        outputPath = dlg.e_outputName.text()

        zipFiles = dlg.chb_zipFile.isChecked()
        if zipFiles:
            outputPath = os.path.splitext(outputPath)[0] + '.zip'

        # Case #1: Copy a single file
        if self.singleFileMode:
            if os.path.exists(outputPath):
                if self.executePopUp(dlg, "File", outputPath) == False:
                    return
                
            outputDir = os.path.dirname(outputPath)
            if not os.path.exists(outputDir):
                os.mkdir(outputDir)

            copyThread = CopyThread(dlg, 1, sourcePath, outputPath, zipFiles, core=self.core)

        # Case #2: Copy entire directory
        elif not self.singleFileMode and not zipFiles:
            sourceDir = os.path.dirname(self.sourcePath[0])
            outputDir = os.path.dirname(outputPath)

            if os.path.exists(outputDir):
                if self.executePopUp(dlg, "Directory", outputDir) == False:
                    return
                
            if not os.path.exists(outputDir):
                os.mkdir(outputDir)
                
            copyThread = CopyThread(dlg, 2, sourceDir, outputDir, zipFiles, core=self.core)

        # Case #3:  Copy and Zip directory
        else:
            sourceDir = os.path.dirname(self.sourcePath[0])
            outputDir = os.path.dirname(outputPath)

            if os.path.exists(outputPath):
                if self.executePopUp(dlg, "File", outputPath) == False:
                    return
                
            if not os.path.exists(outputDir):
                os.mkdir(outputDir)
                
            copyThread = CopyThread(dlg, 3, sourceDir, outputPath, zipFiles, core=self.core)

        copyThread.progressUpdated.connect(dlg.progressBar.setValue)
        thread = threading.Thread(target=copyThread.run)
        thread.start()


    @err_catcher(name=__name__)
    def executePopUp(self, dlg, checkType, output):
        reply = QMessageBox.question(
            dlg,
            f"{checkType} Exists",
            f"The {checkType} already exists:\n\n"
            f"{output}\n\n"
            f"Do you want to overwrite it?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        return reply == QMessageBox.Yes
        


class CopyThread(QObject):
    progressUpdated = Signal(int)

    def __init__(self, dlg, case, sourcePath, outputPath, zipFiles=False, core=None):
        super().__init__()
        self.core = core
        self.dlg = dlg
        self.case = case
        self.sourcePath = sourcePath
        self.outputPath = outputPath
        self.zipFiles = zipFiles
   
    
    @err_catcher(name=__name__)
    def run(self):
        try:
            originalPath = self.sourcePath
            self.tempDir = None

            if self.case == 1:      #   Single File
                if self.zipFiles:

                    filename = os.path.basename(originalPath)
                    zipFilename = os.path.splitext(filename)[0] + '.zip'

                    zipPath = self.executeZip(originalPath, zipFilename)

                    self.dlg.l_status.setText("Copying...")
                    self.copyFile(zipPath, self.outputPath)

                    self.progressUpdated.emit(100)
                    self.dlg.l_status.setText("Complete.")
                    self.dlg.progressBar.setStyleSheet(PROG_GREEN)

                else:
                    outputPathWithExt = self.outputPath
                    self.dlg.l_status.setText("Copying...")
                    self.copyFile(originalPath, outputPathWithExt)
                    self.progressUpdated.emit(100)
                    self.dlg.l_status.setText("Complete.")
                    self.dlg.progressBar.setStyleSheet(PROG_GREEN)



            elif self.case == 2:    #   Directory without Zip
                self.copyDirectory(originalPath, self.outputPath)

            elif self.case ==3:     #   Directory with Zip
                zipFilename = f"{os.path.basename(self.outputPath)}.zip"
                zipPath = self.executeZip(originalPath, zipFilename)

                self.copyFile(zipPath, self.outputPath)

            if self.tempDir:
                shutil.rmtree(self.tempDir)

        except Exception as e:
            self.dlg.l_status.setText("ERROR")
            self.dlg.progressBar.setStyleSheet(PROG_RED)
            self.progressUpdated.emit(100)
            self.core.popup(e)


    @err_catcher(name=__name__)
    def copyFile(self, src, dest, showProg=True):

        if showProg:
            self.progressUpdated.emit(0)
            self.dlg.l_status.setText("Copying...")

        totalSize = os.path.getsize(src)
        copiedSize = 0
        with open(src, 'rb') as srcFile, open(dest, 'wb') as destFile:
            while True:
                chunk = srcFile.read(4096)
                if not chunk:
                    break
                destFile.write(chunk)
                copiedSize += len(chunk)
                if showProg:
                    progressPercentage = int(copiedSize / totalSize * 100)
                    self.progressUpdated.emit(progressPercentage)
        
        if showProg:
            self.dlg.l_status.setText("Complete.")
            self.dlg.progressBar.setStyleSheet(PROG_GREEN)


    @err_catcher(name=__name__)
    def dirFileAmount(self, dirPath):
        try:
            if os.path.isdir(dirPath):
                entries = os.listdir(dirPath)
                files = [entry for entry in entries if os.path.isfile(os.path.join(dirPath, entry))]
                return len(files)
            else:
                return 0

        except FileNotFoundError:
            return 0
        

    @err_catcher(name=__name__)
    def copyDirectory(self, src, dest):
        try:
            self.dlg.l_status.setText("Copying...")

            totalFiles = self.dirFileAmount(src)
            copiedFiles = 0
            for root, _, files in os.walk(src):
                for file in files:
                    srcFile = os.path.join(root, file)
                    # Ensure it's a file and not in a subdirectory
                    if os.path.isfile(srcFile) and os.path.dirname(srcFile) == src:
                        destFile = os.path.join(dest, os.path.relpath(srcFile, src))
                        self.copyFile(srcFile, destFile, showProg=False)
                        copiedFiles += 1
                        progressPercentage = int(copiedFiles / totalFiles * 100)
                        self.progressUpdated.emit(progressPercentage)

            self.dlg.l_status.setText("Complete.")
            self.progressUpdated.emit(100)
            self.dlg.progressBar.setStyleSheet(PROG_GREEN)

        except Exception as e:
            self.dlg.l_status.setText("ERROR.")
            self.progressUpdated.emit(100)
            self.dlg.progressBar.setStyleSheet(PROG_RED)
            self.core.popup(e)  # TESTING


    @err_catcher(name=__name__)
    def executeZip(self, originalPath, zipFilename):                        #   TODO  RENAME FILES

        totalFiles = self.dirFileAmount(originalPath)
        zippedFiles = 0

        self.tempDir = tempfile.mkdtemp(prefix="PrismTemp_")
        zipPath = os.path.join(self.tempDir, zipFilename)

        self.dlg.l_status.setText("Zipping...")

        with zipfile.ZipFile(zipPath, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            if os.path.isdir(originalPath):
                totalFiles = self.dirFileAmount(originalPath)
                zippedFiles = 0

                # Iterate over files directly in the specified directory
                for file in os.listdir(originalPath):
                    file_path = os.path.join(originalPath, file)
                    # Ensure it's a file (not a directory)
                    if os.path.isfile(file_path):
                        arcname = os.path.relpath(file_path, originalPath)
                        zip_file.write(file_path, arcname=arcname)
                        zippedFiles += 1
                        progressPercentage = int(zippedFiles / totalFiles * 100)
                        self.progressUpdated.emit(progressPercentage)

            else:
                self.progressUpdated.emit(20)

                arcname = os.path.basename(originalPath)
                zip_file.write(originalPath, arcname=arcname)

                self.progressUpdated.emit(75)

        return zipPath

########    TODO    ERRORS
    


class AddExportToDirDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        #   Sets up Custon File Selection UI
        self.setWindowTitle("Add Export to Dir Location")

        self.l_name = QLabel("Short Name:")
        self.le_name = QLineEdit()

        self.l_location = QLabel("Location:")
        self.but_location = QPushButton("Select Location")
        self.but_location.clicked.connect(lambda: self.selectLocation(self))

        self.but_ok = QPushButton("OK")
        self.but_ok.clicked.connect(self.accept)

        layout = QVBoxLayout()
        layout.addWidget(self.l_name)
        layout.addWidget(self.le_name)
        layout.addWidget(self.l_location)
        layout.addWidget(self.but_location)
        layout.addWidget(self.but_ok)

        self.setLayout(layout)
        self.setFixedWidth(300)


    def selectLocation(self, origin):
        #   Calls native File Dialog
        windowTitle = "Select Export to Dir Location"
        directory = QFileDialog.getExistingDirectory(origin, windowTitle, QDir.homePath())

        if directory:
            self.l_location.setText(directory)


    def getValues(self):
        name = self.le_name.text()
        location = self.l_location.text()
        return name, location


