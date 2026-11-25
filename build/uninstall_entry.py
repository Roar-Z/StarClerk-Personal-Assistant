"""PyInstaller 的入口。

直接把 uninstaller/main.py 当脚本打包的话，里面的相对导入会失效，
所以绕一层：从包里 import，再调 main()。
"""
from uninstaller.main import main

raise SystemExit(main())
