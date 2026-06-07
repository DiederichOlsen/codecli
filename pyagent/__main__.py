from __future__ import annotations

import sys
from pathlib import Path


if __package__:
    from .cli import main
else:
    # 兼容 `python D:\path\to\pyagent --help` 这类“目录脚本”启动方式。
    # 此时 Python 不会给相对导入设置包上下文，所以需要把项目根目录加入 sys.path。
    package_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(package_dir.parent))
    from pyagent.cli import main

    # 常见误用：`python D:\path\to\pyagent -m pyagent --help`。
    # `-m pyagent` 只有放在解释器后面才生效；放在脚本路径后面会变成普通参数。
    # 这里温和地吞掉它，让用户仍然能看到预期的 CLI 输出。
    if sys.argv[1:3] == ["-m", "pyagent"]:
        del sys.argv[1:3]


if __name__ == "__main__":
    raise SystemExit(main())
