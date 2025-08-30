import os
import io
import csv
import asyncio
import logging
from typing import Optional, List, Tuple

import pandas as pd
import discord
from discord import app_commands

from checker import run_checks  # <-- uses our new checker.py

# ---------------------- Logging ----------------------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("goethe-bot")

# ---------------------- Config -----------------------
MASTER_FILE = os.getenv("MASTER_FILE", "final_verified_list.csv")

def _load_token() -> str:
    token = os.getenv("DISCORD_TOKEN")
    if token and token.strip():
        return token.strip()

    env_path = os.path.abspath(".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8-sig", errors="replace") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip().lstrip("\ufeff") == "DISCORD_TOKEN":
                    v = v.strip().strip('"').strip("'")
                    if v:
                        return v
    raise RuntimeError(
        "DISCORD_TOKEN not found.\n"
        "Set it as an environment variable or put one line in .env:\n"
        "DISCORD_TOKEN=your_token_here"
    )

TOKEN = _load_token()

# ---------------------- Discord ----------------------
intents = discord.Intents.default()
# Needed because we'll read a follow-up plaintext message if user didn't upload the file:
intents.message_content = True

class GoetheBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.last_summary: Optional[str] = None
        self.last_df: Optional[pd.DataFrame] = None

    async def setup_hook(self):
        try:
            await self.tree.sync()
            log.info("Commands synced successfully")
        except Exception as e:
            log.error(f"Failed to sync commands: {e}")

bot = GoetheBot()

@bot.event
async def on_ready():
    print(f"✅ Bot logged in as {bot.user}")
    log.info(f"✅ Bot logged in as {bot.user}")

# ---------------------- Helpers ----------------------
def parse_email_password_lines(text: str) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        try:
            email, pwd = line.split("|", 1)
            email, pwd = email.strip(), pwd.strip()
            if email and pwd:
                pairs.append((email, pwd))
        except ValueError:
            continue
    return pairs

def parse_attachment_bytes(content: bytes, filename: str) -> List[Tuple[str, str]]:
    try:
        text = content.decode("utf-8", errors="replace")
        if filename.lower().endswith(".csv"):
            reader = csv.reader(io.StringIO(text))
            pairs: List[Tuple[str, str]] = []
            for row in reader:
                if not row:
                    continue
                if len(row) == 1 and "|" in row[0]:
                    email, pwd = row[0].split("|", 1)
                elif len(row) >= 2:
                    email, pwd = row[0], row[1]
                else:
                    continue
                email, pwd = email.strip(), pwd.strip()
                if email and pwd:
                    pairs.append((email, pwd))
            return pairs
        else:
            return parse_email_password_lines(text)
    except Exception:
        return []

async def collect_user_input(interaction: discord.Interaction) -> List[Tuple[str, str]]:
    await interaction.followup.send(
        "📩 Send your credentials as `email|password` (one per line). You have **30 seconds**.",
        ephemeral=True
    )

    def check(m: discord.Message) -> bool:
        return m.author.id == interaction.user.id and m.channel.id == interaction.channel_id

    try:
        msg = await bot.wait_for("message", check=check, timeout=30)
        return parse_email_password_lines(msg.content or "")
    except asyncio.TimeoutError:
        await interaction.followup.send("⏳ Timed out waiting for input.", ephemeral=True)
        return []

# ---------------------- Commands ----------------------
@bot.tree.command(name="verify", description="Verify Goethe login credentials")
@app_commands.describe(
    file="Upload .txt or .csv file with lines like email|password",
    inline_block="Paste credentials directly (email|password per line)"
)
async def verify_command(
    interaction: discord.Interaction,
    file: Optional[discord.Attachment] = None,
    inline_block: Optional[str] = None
):
    await interaction.response.defer(thinking=True, ephemeral=False)

    pairs: List[Tuple[str, str]] = []

    # From file
    if file:
        try:
            if not (file.filename.lower().endswith(".txt") or file.filename.lower().endswith(".csv")):
                await interaction.followup.send("❌ Please upload a .txt or .csv file.", ephemeral=True)
                return
            data = await file.read()
            pairs = parse_attachment_bytes(data, file.filename)
        except Exception as e:
            log.error(f"Error reading file: {e}")

    # From inline text
    if not pairs and inline_block:
        pairs = parse_email_password_lines(inline_block)

    # Ask interactively if still empty
    if not pairs:
        pairs = await collect_user_input(interaction)

    if not pairs:
        await interaction.followup.send("❌ No valid credentials found.", ephemeral=True)
        return

    await interaction.followup.send(f"⏳ Checking **{len(pairs)}** account(s). This may take a moment...")

    # Run checks
    try:
        results = await run_checks(pairs)
    except Exception:
        log.exception("run_checks failed")
        await interaction.followup.send("❌ An unexpected error occurred during verification.", ephemeral=True)
        return

    # Build DataFrame + summary
    df = pd.DataFrame(results, columns=["Email", "Status", "Reason"])
    bot.last_df = df.copy()

    total = len(df)
    successes = int((df["Status"] == "success").sum())
    failures = total - successes
    rate = (successes / total * 100) if total else 0.0

    summary = (
        f"📊 **Verification Results**\n"
        f"✅ Success: **{successes}/{total}**\n"
        f"❌ Failed: **{failures}/{total}**\n"
        f"📈 Rate: **{rate:.1f}%**"
    )
    bot.last_summary = summary

    await interaction.followup.send(summary)

    if total <= 10:
        # Inline details for small batches
        lines = ["\n**Detailed Results:**"]
        for _, row in df.iterrows():
            lines.append(f"- `{row['Email']}` → **{row['Status']}** ({row['Reason']})")
        await interaction.followup.send("\n".join(lines))
    else:
        # Attach CSV for large batches
        csv_buf = io.StringIO()
        df.to_csv(csv_buf, index=False)
        csv_bytes = csv_buf.getvalue().encode("utf-8")
        await interaction.followup.send(
            content="📎 Attached CSV with full results.",
            file=discord.File(io.BytesIO(csv_bytes), filename="goethe_verification_results.csv")
        )

    # Persist locally (optional)
    try:
        df.to_csv(MASTER_FILE, index=False)
        log.info(f"Saved results to {MASTER_FILE}")
    except Exception as e:
        log.warning(f"Could not save to {MASTER_FILE}: {e}")

@bot.tree.command(name="export", description="Export the last verification results as CSV")
async def export_command(interaction: discord.Interaction):
    if bot.last_df is None or bot.last_df.empty:
        await interaction.response.send_message("ℹ️ No previous results to export. Run `/verify` first.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True, ephemeral=False)

    csv_buf = io.StringIO()
    bot.last_df.to_csv(csv_buf, index=False)
    csv_bytes = csv_buf.getvalue().encode("utf-8")
    await interaction.followup.send(
        content=bot.last_summary or "📎 Exporting last results.",
        file=discord.File(io.BytesIO(csv_bytes), filename="last_goethe_results.csv")
    )

# ---------------------- Entrypoint -------------------
if __name__ == "__main__":
    bot.run(TOKEN)
