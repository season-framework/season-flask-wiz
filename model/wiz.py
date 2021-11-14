import season

import base64
import lesscpy
import sass
import dukpy
from six import StringIO
import json
import os
import pypugjs
import datetime
from werkzeug.routing import Map, Rule
import time

def addtabs(v, size=1):
    for i in range(size):
        v =  "    " + "\n    ".join(v.split("\n"))
    return v

def spawner(code, namespace, logger, **kwargs):
    fn = {'__file__': namespace, '__name__': namespace, 'print': logger}
    for key in kwargs: fn[key] = kwargs[key]
    exec(compile(code, namespace, 'exec'), fn)
    return fn


"""WIZ Process API
: this function used in wiz interfaces code editors and frameworks.

- log(*args)
- render(target_id, namespace, **kwargs)
- dic(key)
- controller(namespace)
- theme()
- resources(path)
"""

class Wiz(season.stdClass):
    def __init__(self, wiz):
        framework = wiz.framework
        self.__wiz__ = wiz
        
        self.flask = framework.flask
        self.socketio = framework.socketio
        self.flask_socketio = framework.flask_socketio

        self.PATH = framework.core.PATH
        self.request = framework.request
        self.response = framework.response
        self.response.render = self.__render__
        self.config = framework.config
        self.__logger__ = self.logger("instance")

    def logger(self, tag=None, log_color=94):
        class logger:
            def __init__(self, tag, log_color, wiz):
                self.tag = tag
                self.log_color = log_color
                self.wiz = wiz

            def log(self, *args):
                tag = self.tag
                log_color = self.log_color
                wiz = self.wiz
                
                if tag is None: tag = "undefined"
                tag = "[wiz]" + tag
                
                args = list(args)
                for i in range(len(args)): 
                    args[i] = str(args[i])
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
                logdata = f"\033[{log_color}m[{timestamp}]{tag}\033[0m " + " ".join(args)
                print(logdata)

                branch = wiz.__wiz__.branch()
                wiz.socketio.emit("log", logdata + "\n", namespace="/wiz", to=branch, broadcast=True)
                
        return logger(tag, log_color, self).log

    def __dic__(self, mode, app_id):
        class dic:
            def __init__(self, wizinst, mode, app_id):
                self.__wizinst__ = wizinst
                self.mode = mode
                self.app_id = app_id
            
            def dic(self, key):
                wiz = self.__wizinst__.__wiz__
                cache = self.__wizinst__.cache

                if mode is None or app_id is None:
                    return ""

                language = self.__wizinst__.request.language()
                language = language.lower()
                
                # TODO: READ FROM CACHE

                if mode == 'route': 
                    inst = wiz.cls.Route(wiz.framework)
                else: 
                    inst = wiz.cls.App(wiz.framework)
                dic = inst.dic(app_id)

                if language in dic: dic = dic[language]
                if "default" in dic: dic = dic["default"]

                key = key.split(".")
                tmp = dic
                for k in key:
                    if k not in tmp:
                        return ""
                    tmp = tmp[k]

                return tmp

        dicinst = dic(self, mode, app_id)
        return dicinst.dic

    def __render__(self, *args, **kwargs):
        wiz = self.__wiz__
        framework = wiz.framework
        view = self.render(*args, **kwargs)
        framework.response.send(view, "text/html")

    def __compiler__(self, codelang, code, **kwargs):
        logger = self.logger(f"[compiler][{codelang}]")
        try:
            if code is None: return ""
            if len(code) == 0: return code
            wiz = self.__wiz__
            fs = wiz.framework.model("wizfs", module="wiz").use(f"wiz/compiler")
            if fs.isfile(f"{codelang}.py") == False:
                return code
            compiler = fs.read(f"{codelang}.py")
            compiler = spawner(compiler, "season.wiz.compiler", logger)
            return compiler['compile'](self, code, kwargs)
        except Exception as e:
            logger(e)
            raise e

    def controller(self, namespace):
        wiz = self.__wiz__
        fs = wiz.storage()
        fsns = fs.namespace
        fsns = os.path.join(fsns, "interfaces/controller")
        fs = fs.use(fsns)
        code = fs.read(namespace + ".py")
        logger = self.logger(f"[controller][{namespace}]", 94)
        obj = spawner(code, 'season.wiz.controller', logger, wiz=self)
        return obj['Controller']

    def model(self, namespace):
        wiz = self.__wiz__
        fs = wiz.storage()
        fsns = fs.namespace
        fsns = os.path.join(fsns, "interfaces/model")
        fs = fs.use(fsns)
        code = fs.read(namespace + ".py")
        logger = self.logger(f"[model][{namespace}]", 94)
        obj = spawner(code, 'season.wiz.model', logger, wiz=self)
        return obj['Model']

    def theme(self, themename, layoutname, viewpath, view=None):
        layout = self.layout(themename, layoutname, viewpath, view=view)
        return layout

    def layout(self, themename, layoutname, viewpath, view=None):
        wiz = self.__wiz__
        framework = wiz.framework
        cache = wiz.cache

        THEME_BASEPATH = os.path.join(wiz.branchpath(), "themes")
        namespace = f"{themename}/layout/{layoutname}/{viewpath}"

        layout = cache.get(f"themes/{namespace}")
        
        if layout is None:
            _, ext = os.path.splitext(viewpath)
            if ext[0] == ".": ext = ext[1:]
            ext = ext.lower()

            fs = wiz.storage().use(THEME_BASEPATH)
            layout = fs.read(namespace)
            layout = self.__compiler__(ext, layout)
            cache.set(f"themes/{namespace}", layout)
        
        kwargs = framework.response.data.get()
        kwargs['wiz'] = self
        if view is not None:
            kwargs['view'] = view
        layout = framework.response.template_from_string(layout, **kwargs)
        return layout

    def render(self, *args, **kwargs):
        if len(args) == 0: return ""

        wiz = self.__wiz__
        cache = wiz.cache
        framework = wiz.framework

        app_id = args[0] # app unique id or app namespace

        # find by namespace and id
        app = cache.get(f"apps/bynamespace/{app_id}")
        if app is None: app = cache.get(f"apps/byid/{app_id}")

        # if cache not exists, find app
        if app is None:
            inst = wiz.cls.App(framework)
            app = inst.get(app_id)

            app_id = app['package']['id']
            app_namespace = app['package']['namespace']
            namespace = str(app_namespace)  # namespace for ui
            if len(args) > 1: namespace = args[1]
            render_id = app['package']['render_id'] = app_id + "_" + framework.lib.util.randomstring(16)
        
            # compile controller
            controller = app['controller']
            controller = addtabs(controller)
            controller = f"import season\ndef process(wiz, **kwargs):\n    framework = wiz\n{controller}\n    return kwargs"
            app['controller'] = controller

            # compile codes
            def load_property(key, default=None):
                try:
                    return app['package']['properties'][key]
                except:
                    return default
            
            codelang_html = load_property("html", "pug")
            codelang_css = load_property("css", "scss")
            codelang_js = load_property("js", "javascript")

            compile_args = dict()
            compile_args['app_id'] = app_id
            compile_args['app_namespace'] = app_namespace
            compile_args['namespace'] = namespace
            compile_args['render_id'] = render_id

            # compile to default language
            if codelang_html != 'html': app['html'] = self.__compiler__(codelang_html, app['html'], **compile_args)
            if codelang_css != 'css': app['css'] = self.__compiler__(codelang_css, app['css'], **compile_args)
            if codelang_js != 'javascript': app['js'] = self.__compiler__(codelang_js, app['js'], **compile_args)

            # compile reformat default language 
            app['html'] = self.__compiler__('html', app['html'], **compile_args)
            app['css'] = self.__compiler__('css', app['css'], **compile_args)
            app['js'] = self.__compiler__('javascript', app['js'], **compile_args)

            # save cache
            cache.set(f"apps/byid/{app_id}", app)
            cache.set(f"apps/bynamespace/{app_namespace}", app)

        app_id = app['package']['id']
        app_namespace = app['package']['namespace']
        namespace = str(app_namespace)  # namespace for ui
        if len(args) > 1: namespace = args[1]
        render_id = app['package']['render_id']

        if self.app_id is None:
            self.app_id = app_id

        render_theme = None
        if self.render_theme is None:
            if 'theme' in app['package']:
                render_theme = self.render_theme = app['package']['theme']
        
        ctrl = None
        if 'controller' in app['package']:
            ctrl = app['package']['controller']
            ctrl = self.controller(ctrl)
            if ctrl is not None:
                ctrl = ctrl()
                ctrl.__startup__(self)

        logger = self.logger(f"[app][{app_namespace}]", 93)
        dic = self.__dic__('app', app_id)
        controllerfn = spawner(app['controller'], 'season.wiz.app', logger, controller=ctrl, dic=dic)
        kwargs = controllerfn['process'](self, **kwargs)
        kwargs['query'] = framework.request.query()
        
        kwargsstr = json.dumps(kwargs, default=self.json_default)
        kwargsstr = kwargsstr.encode('ascii')
        kwargsstr = base64.b64encode(kwargsstr)
        kwargsstr = kwargsstr.decode('ascii')

        kwargs['wiz'] = self

        view = app['html']
        js = app['js']
        css = app['css']

        view = f"""{view}
<script src="/resources/wiz/libs/wiz.js"></script>
<script type="text/javascript">
    {js}
</script>
<style>{css}</style>
        """

        view = framework.response.template_from_string(view, kwargs=kwargsstr, **kwargs)

        if render_theme is None:
            return view

        render_theme = render_theme.split("/")
        themename = render_theme[0]
        layoutname = render_theme[1]

        view = self.theme(themename, layoutname, 'layout.pug', view=view)
        return view



"""Data Management APIs

- get(app_id, mode='app')
- rows(mode='app')
- update(info, mode='app')
- delete(app_id, mode='app')
"""
class DataManager:
    def __init__(self, wiz):
        self.__wiz__ = wiz
    
    def inst(self, mode):
        wiz = self.__wiz__
        if mode == 'route': inst = wiz.cls.Route(wiz.framework)
        else: inst = wiz.cls.App(wiz.framework)
        return inst

    def get(self, app_id, mode='app'):
        wiz = self.__wiz__
        branch = wiz.branch()
        inst = self.inst(mode)
        inst.checkout(branch)
        app = inst.get(app_id)
        return app

    def rows(self, mode='app'):
        wiz = self.__wiz__
        branch = wiz.branch()
        inst = self.inst(mode)
        inst.checkout(branch)
        apps = inst.rows()
        return apps

    def update(self, info, mode='app'):
        wiz = self.__wiz__
        branch = wiz.branch()
        inst = self.inst(mode)
        inst.checkout(branch)
        apps = inst.update(info)
        return apps

    def delete(self, app_id, mode='app'):
        wiz = self.__wiz__
        branch = wiz.branch()
        inst = self.inst(mode)
        inst.checkout(branch)
        inst.delete(app_id)



"""WIZ Cache API
: this class used in local only.

- get(key, default=None)
- set(key, value)
- flush()
"""
class CacheControl:
    def __init__(self, wiz):
        self.__wiz__ = wiz
        self.cache = wiz.framework.cache
        self.enabled = False
        branch = wiz.branch()
        if 'wiz' not in self.cache:
            self.cache.wiz = season.stdClass()
        if branch not in self.cache.wiz:
            self.cache.wiz[branch] = season.stdClass()

    def enable(self, enabled):
        self.enabled = enabled
        return self

    def fs(self):
        wiz = self.__wiz__
        branch = wiz.branch()
        return wiz.framework.model("wizfs", module="wiz").use(f"wiz/cache/render/{branch}")

    def get(self, key, default=None):
        wiz = self.__wiz__
        if wiz.is_dev() and self.enabled == False:
            return None
        branch = wiz.branch()
        if branch in self.cache.wiz:
            if key in self.cache.wiz[branch]:
                return self.cache.wiz[branch][key]
        try:
            fs = self.fs()
            return fs.read_pickle(f"{key}.pkl")
        except:
            pass
        return default
        
    def set(self, key, value):
        wiz = self.__wiz__
        branch = wiz.branch()
        try:
            fs = self.fs()
            fs.write_pickle(f"{key}.pkl", value)
            self.cache.wiz[branch][key] = value
            return True
        except:
            pass
        return False
        
    def flush(self):
        wiz = self.__wiz__
        branch = wiz.branch()
        try:
            fs = self.fs()
            fs.remove(".")
        except:
            pass
        self.cache.wiz[branch] = season.stdClass()


""" WIZ Model used in framework level
"""
class Model:
    def __init__(self, framework):
        wizfs = framework.model("wizfs", module="wiz")
        
        # load package info
        try:
            opts = wizfs.use("modules/wiz").read_json("wiz-package.json")
        except:
            opts = {}
            
        # set variables
        self.package = season.stdClass(opts)
        self.framework = framework 

        # load config
        self.config = config = framework.config.load("wiz")

        # set storage
        wizsrc = config.get("src", "wiz")
        self.path = season.stdClass()
        self.path.root = wizsrc
        self.path.apps = os.path.join(wizsrc, "apps")
        self.path.cache = os.path.join(wizsrc, "cache")
        
        # set Env
        self.env = season.stdClass()
        self.env.DEVTOOLS = config.get("devtools", False)

        try:
            self.env.DEVMODE = framework.request.cookies("season-wiz-devmode", "false")
            if self.env.DEVMODE == "false": self.env.DEVMODE = False
            else: self.env.DEVMODE = True
        except:
            self.env.DEVMODE = False

        try: self.env.BRANCH = framework.request.cookies("season-wiz-branch", "master")
        except: self.env.BRANCH = "master"

        self.cls = season.stdClass()

        modulename = framework.modulename
        framework.modulename = "wiz"
        self.cls.Route = framework.lib.app.Route
        self.cls.App = framework.lib.app.App
        framework.modulename = modulename

        self.cache = CacheControl(self)
        self.data = DataManager(self)
        self.instances = []


    """WIZ Configuration API
    : configuration api used in wiz module.

    - set_env(name, value)  :
    - is_dev()              :
    - set_dev(DEVMODE)      :
    - checkout(branch)      :
    - themes()              :
    """

    def set_env(self, name, value=None):
        if value is None:
            if name in self.env:
                del self.env[name]
        else:
            self.env[name] = value
    
    def is_dev(self):
        return self.env.DEVMODE

    def set_dev(self, DEVMODE):
        """set development mode.
        :param DEVMODE: string variable true/false
        """
        self.framework.response.cookies.set("season-wiz-devmode", DEVMODE)
        if DEVMODE == "false": self.env.DEVMODE = False
        else: self.env.DEVMODE = True

    def branch(self):
        return self.env.BRANCH

    def checkout(self, branch):
        """checkout branch
        :param branch: string variable of branch name
        """
        self.framework.response.cookies.set("season-wiz-branch", branch)
        self.env.BRANCH = branch

        # route_inst = self.cls.Route(self.framework)
        # route_inst.checkout(branch)

        # route_inst = self.cls.App(self.framework)
        # route_inst.checkout(branch)

    def themes(self):
        framework = self.framework
        BASEPATH = os.path.join(self.branchpath(), "themes")
        fs = framework.model("wizfs", module="wiz").use(BASEPATH)
        themes = fs.list()
        res = []
        for themename in themes:
            layoutpath = os.path.join(BASEPATH, themename, 'layout')
            fs = fs.use(layoutpath)
            layouts = fs.list()
            for layout in layouts:
                fs = fs.use(os.path.join(layoutpath, layout))
                if fs.isfile('layout.pug'):
                    res.append(f"{themename}/{layout}")
        return res

    def controllers(self):
        try:
            fs = self.storage()
            fsns = fs.namespace
            fsns = os.path.join(fsns, "interfaces/controller")
            fs = fs.use(fsns)
            rows = fs.files(recursive=True)
            ctrls = []
            for row in rows:
                if row[0] == "/": row = row[1:]
                name, ext = os.path.splitext(row)
                if ext == ".py":
                    ctrls.append(name)
            return ctrls
        except:
            pass
        return []

    def branchpath(self):
        branch = self.branch()
        return f"wiz/branch/{branch}"

    def storage(self):
        framework = self.framework
        branchpath = self.branchpath()
        return framework.model("wizfs", module="wiz").use(branchpath)

    # TODO
    def target_version(self):
        if self.env.DEVMODE:
            return "master"
        return "master"    


    """Process API
    : this function used in framework.
    
    - api(app_id)
    - route()
    """

    def api(self, app_id):
        app = self.data.get(app_id)
        if app is None or 'api' not in app:
            return None

        app_id = app['package']['id']
        
        view_api = app['api']
        if len(view_api) == 0:
            return None

        wiz = self.instance()
        wiz.app_id = app_id

        ctrl = None
        if 'controller' in app['package']:
            ctrl = app['package']['controller']
            ctrl = wiz.controller(ctrl)
            if ctrl is not None:
                ctrl = ctrl()
                ctrl.__startup__(wiz)
        
        namespace = app['package']['namespace']
        logger = wiz.logger(f"[app][{namespace}][api]")
        dic = wiz.__dic__('app', app_id)
        apifn = spawner(view_api, 'season.wiz.app.api', logger, controller=ctrl, dic=dic)
        return apifn, wiz

    def route(self):
        """select route wiz component and render view.
        this function used in season flask's filter.
        """

        cache = self.cache
        framework = self.framework

        # get request uri
        request_uri = framework.request.uri()

        # ignored for wiz admin interface.
        if request_uri.startswith("/wiz/") or request_uri == '/wiz':
            return

        routes = self.routes()
        app_id, segment = routes(request_uri)

        # if not found, proceed default policy of season flask
        if app_id is None:
            return

        # set segment for wiz component
        framework.request.segment = season.stdClass(segment)
        
        # build controller from route code
        route = cache.get(f"routes/{app_id}")

        if route is None:
            inst = self.cls.Route(self.framework)
            route = inst.get(app_id)
            controller = route['controller']
            controller = addtabs(controller)
            controller = f"import season\ndef process(wiz):\n    framework = wiz\n{controller}"
            route['controller'] = controller
            cache.set(f"routes/{app_id}", route)
            
        # setup logger
        wiz = self.instance()
        wiz.route_id = app_id

        ctrl = None
        if 'controller' in route['package']:
            ctrl = route['package']['controller']
            ctrl = wiz.controller(ctrl)
            if ctrl is not None:
                ctrl = ctrl()
                ctrl.__startup__(wiz)
        
        logger = wiz.logger(f"[route][{request_uri}]", 93)
        dic = wiz.__dic__('route', app_id)
        controllerfn = spawner(route['controller'], 'season.wiz.route', logger, controller=ctrl, dic=dic)
        controllerfn['process'](wiz)


    """WIZ Private API
    : this function used in local only.
    
    - routes(): return all routes
    - instance(): return wiz api object
    """

    def routes(self):
        """load all routes in branch.
        this function used in local only.
        """

        cache = self.cache
        branch = self.branch()

        # load from cache, if `devmode` false
        routes = cache.get("routes")

        # if routes not in cache or `devmode` true, load routes            
        if routes is None:
            inst = self.cls.Route(self.framework)
            rows = inst.rows()
            routes = []
            for row in rows:
                obj = dict()
                obj['route'] = row['package']['route']
                obj['id'] = row['package']['id']
                routes.append(obj)
            cache.set("routes", routes)

        # generate url map
        url_map = []
        for i in range(len(routes)):
            info = routes[i]
            route = info['route']
            if route is None: continue
            if len(route) == 0: continue

            endpoint = info["id"]
            if route[-1] == "/":
                url_map.append(Rule(route[:-1], endpoint=endpoint))
            elif route[-1] == ">":
                rpath = route
                while rpath[-1] == ">":
                    rpath = rpath.split("/")[:-1]
                    rpath = "/".join(rpath)
                    url_map.append(Rule(rpath, endpoint=endpoint))
                    if rpath[-1] != ">":
                        url_map.append(Rule(rpath + "/", endpoint=endpoint))
            url_map.append(Rule(route, endpoint=endpoint))
        
        url_map = Map(url_map)
        url_map = url_map.bind("", "/")

        def matcher(url):
            try:
                endpoint, kwargs = url_map.match(url, "GET")
                return endpoint, kwargs
            except:
                return None, {}
        
        return matcher

    def instance(self):
        inst = Wiz(self)
        self.instances.append(inst)
        return inst