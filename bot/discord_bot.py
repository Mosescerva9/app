"""Discord gateway listener for low-latency options alerts."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import discord

from bot.config import Settings
from bot.engine import TradeEngine

logger = logging.getLogger(__name__)


class AlertBot(discord.Client):
    def __init__(self, settings: Settings, engine: TradeEngine) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.messages = True
        super().__init__(intents=intents)
        self.settings = settings
        self.engine = engine

    async def on_ready(self) -> None:
        logger.info(
            "Discord connected as %s — monitoring guild=%s channels=%s",
            self.user,
            self.settings.discord_guild_id or "any",
            sorted(self.settings.discord_channel_ids) or "all visible",
        )

    def _allowed_message(self, message: discord.Message) -> bool:
        if message.author == self.user:
            return False
        if self.settings.discord_guild_id is not None:
            if message.guild is None or message.guild.id != self.settings.discord_guild_id:
                return False
        if self.settings.discord_channel_ids and message.channel.id not in self.settings.discord_channel_ids:
            return False
        if self.settings.discord_alert_author_ids:
            if message.author.id not in self.settings.discord_alert_author_ids:
                return False
        return True

    async def on_message(self, message: discord.Message) -> None:
        if not self._allowed_message(message):
            return
        # Run trading I/O off the event loop so Discord heartbeats stay healthy.
        await asyncio.to_thread(self.engine.handle_message, message)

    async def on_message_edit(
        self, before: discord.Message, after: discord.Message
    ) -> None:
        # Some alert bots edit embeds after posting; treat edits as new if unprocessed.
        if not self._allowed_message(after):
            return
        await asyncio.to_thread(self.engine.handle_message, after)


async def run_bot(settings: Settings, engine: TradeEngine) -> None:
    bot = AlertBot(settings, engine)
    async with bot:
        await bot.start(settings.discord_bot_token)
