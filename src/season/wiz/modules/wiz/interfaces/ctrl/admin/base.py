import season

class view(season.interfaces.wiz.ctrl.base.view):
    def __startup__(self, framework):
        super().__startup__(framework)
        
        if len(self.config.data) == 0: framework.response.redirect("/wiz/install")
        if self.config.data.acl is not None: self.config.data.acl(framework)

        menus = self.config.get("topmenus", [])
        self.topnav(menus)
        
        menus = []
        menus.append({"title": "Workspace", "url": '/wiz/admin/workspace', 'pattern': r'^/wiz/admin/workspace' })
        menus.append({"title": "Branch", "url": '/wiz/admin/branch', 'pattern': r'^/wiz/admin/branch' })
        menus.append({"title": "Setting", "url": '/wiz/admin/setting', 'pattern': r'^/wiz/admin/setting' })
        self.nav(menus)

        category = self.config.get("category")
        branch = framework.wiz.workspace.branch()
        branches = framework.wiz.workspace.branches()
        self.exportjs(CATEGORIES=category, BRANCH=branch, BRANCHES=branches)
        framework.response.data.set(branches=framework.wiz.workspace.branches())
    
class api(season.interfaces.wiz.ctrl.base.api):
    def __startup__(self, framework):
        super().__startup__(framework)
        if self.config.data.acl is not None: self.config.data.acl(framework)
