from os import getcwd, listdir

import Manager
import Setup

class Application:
    def __init__(self) -> None:
        curr = str(getcwd())
        files = listdir(curr)
        if 'config.cfg' in files:
            self.startup()
        else:
            self.setup()

    def setup(self):
        sw = Setup.SetupWindow()
        sw.setup()
        sw.mainloop()

    def startup(self):
        mg = Manager.Startup()
        mg.mainloop()

if __name__=="__main__":
    app = Application()