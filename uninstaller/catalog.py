"""卸载时可以勾选删哪些东西。

顺序是按"从轻到重"排的：日志、统计这种删了没事的放前面，
知识库、记忆、程序文件这种删了就回不来的放后面。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Item:
    key: str
    title: str
    desc: str
    level: str  # safe / warn / danger
    default: bool  # 打开时默认勾不勾
    note: str = ""  # 勾上之后展开的那句警告
    needs_closed: bool = True  # 要不要先关主程序
    frozen_only: bool = False  # 只在打包版里出现

    def to_dict(self) -> dict:
        return asdict(self)


ITEMS: tuple[Item, ...] = (
    Item(
        "usage",
        "用量与错误记录",
        "模型调用次数、token 统计、程序报错记录",
        "safe",
        True,
        needs_closed=False,
    ),
    Item(
        "logs",
        "运行日志",
        "logs 目录下的文本日志，排查问题时才用得上",
        "safe",
        True,
        needs_closed=False,
    ),
    Item(
        "sessions",
        "会话记录",
        "所有对话标题和聊天内容",
        "warn",
        False,
        "删掉后对话列表会清空，这些聊天记录找不回来",
    ),
    Item(
        "tasks",
        "巡检任务",
        "定时任务的配置、上次运行结果和历史记录",
        "warn",
        False,
        "任务会全部取消，之后要重新建",
    ),
    Item(
        "mindmaps",
        "思维导图",
        "从资料生成的导图文件和缓存",
        "warn",
        False,
        "导图文件删了就没了，要重新生成",
    ),
    Item(
        "memory",
        "大模型记忆",
        "对话里总结出来的偏好、事实，以及它们的向量索引",
        "danger",
        False,
        "助手会忘记之前记住的东西，这部分没有备份",
    ),
    Item(
        "knowledge",
        "本地知识库",
        "资料分块、向量索引，以及上传的原文件",
        "danger",
        False,
        "资料和索引一起删，以后要重新导入文件并重新生成向量",
    ),
    Item(
        "config",
        "模型配置",
        ".env 里的接口地址、API Key、热键和数据目录设置",
        "warn",
        False,
        "删掉后按默认配置启动，Key 和自定义地址要重新填",
        needs_closed=True,
    ),
    Item(
        "license",
        "授权信息",
        "激活码、当前档位和本机机器码",
        "warn",
        False,
        "会退回游客档位，需要重新输入激活码",
        needs_closed=True,
    ),
    Item(
        "program",
        "程序文件",
        "整个安装目录，包括 StarClerk.exe 和这个卸载程序",
        "danger",
        False,
        "程序和上面没勾选的数据会被一起删掉，删完这个文件夹就空了",
        needs_closed=True,
        frozen_only=True,
    ),
)

BY_KEY = {i.key: i for i in ITEMS}


def items(frozen: bool) -> list[dict]:
    """源码目录下不给删程序文件，那是把人仓库删了。"""
    return [i.to_dict() for i in ITEMS if frozen or not i.frozen_only]


def keys(frozen: bool) -> list[str]:
    return [i["key"] for i in items(frozen)]


def data_keys(frozen: bool) -> list[str]:
    """"删除所有数据"不含程序文件，程序是卸载时才动。"""
    return [i["key"] for i in items(frozen) if i["key"] != "program"]
