import os
import time
from werkzeug.routing import Map, Rule

import season

from season.component.obj import InstanceObject

from season.component.plugin.request import Request
from season.component.plugin.response import Response

from season.component.plugin.app import App
from season.component.plugin.route import Route
from season.component.plugin.config import Config
from season.component.plugin.compiler import Compiler
from season.component.plugin.theme import Theme

class plugin(InstanceObject):
    def __init__(self, server, **kwargs):
        super().__init__(server, **kwargs)

        wizurl = server.config.wiz.url
        if wizurl[-1] == "/": wizurl = wizurl[:-1]
        self.url = wizurl

    def load(self, id):
        plug = plugin(self.server)
        plug.id = id
        return plug

    def initialize(self):
        self.request = Request(self)
        self.response = Response(self)
        self.route = Route(self)
        self.app = App(self)
        self.compiler = Compiler(self)
        self.theme = Theme(self)

    def config(self, namespace="config"):
        c = Config.load(namespace)
        return c

    def basepath(self):
        return os.path.join(season.path.project, 'plugin', 'modules', self.id)
        
    def tag(self):
        return "wiz-plugin"
