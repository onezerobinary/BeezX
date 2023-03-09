"""Beez blockchain - message pull digital asset junk."""

from __future__ import annotations
from typing import TYPE_CHECKING

from beez.socket.messages.message import Message
from beez.socket.messages.message_type import MessageType

if TYPE_CHECKING:
    from beez.socket.socket_connector import SocketConnector
    from beez.block.block import Block


class MessagePullJunk(Message):  # pylint: disable=too-few-public-methods
    """Message pull digital asset junk."""

    def __init__(
        self,
        sender_connector: SocketConnector,
        message_type: MessageType,
        junk_name: str,
        file_name: str
    ):
        super().__init__(sender_connector, message_type)
        self.junk_name = junk_name
        self.file_name = file_name
        
