from langchain_core.messages import AIMessage

from app.domain.models import NextAction
from app.graph.state import TravelState, TravelStatePatch


def abort(_: TravelState) -> TravelStatePatch:
    return {
        "messages": [AIMessage(content="暂时无法确定要执行的旅游任务，请换一种方式描述。")],
        "next_action": NextAction.ABORT,
    }
