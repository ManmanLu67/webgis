"""迁移相关的知识集中在这里。

表结构只有迁移这一条路。启动时如果发现库里的 alembic 版本落后于代码 head，
就该拒绝启动，而不是带着漂移跑——等某条查询报"no such column"就太晚了。

Alembic 的目录布局与 ini 位置属于部署知识，所以放在这里，`app.main` 只调用
`current_head()` 与 `check_schema()`，不需要知道 alembic 长什么样。
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import OperationalError

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _script_directory() -> ScriptDirectory:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return ScriptDirectory.from_config(config)


def current_head() -> str | None:
    return _script_directory().get_current_head()


def applied_revisions(engine: Engine) -> set[str]:
    with engine.connect() as connection:
        return {
            row[0]
            for row in connection.execute(text("SELECT version_num FROM alembic_version"))
        }


def check_schema(engine: Engine) -> str | None:
    """比对当前库的 alembic 版本与代码里的 head，返回问题描述或 None。

    库是空的返回 None：那是还没迁移过，`alembic upgrade head` 建出来即可。
    """
    try:
        with engine.connect() as connection:
            tables = inspect(connection).get_table_names()
            if "alembic_version" not in tables:
                if not tables:
                    return None
                return "数据库非空但没有 alembic_version，请先跑 alembic upgrade head"
    except OperationalError as exc:  # pragma: no cover - 依赖真实数据库故障
        return f"无法读取数据库版本：{exc}"
    head = current_head()
    if not head:
        return None
    recorded = applied_revisions(engine)
    if head not in recorded:
        recorded_text = "、".join(sorted(recorded)) or "空"
        return f"schema 版本 {recorded_text} 落后于代码 head {head}，请跑 alembic upgrade head"
    return None