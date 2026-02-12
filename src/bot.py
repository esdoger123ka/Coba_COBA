from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Tuple

from zoneinfo import ZoneInfo
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from .config import load_config
from .data_loader import load_orders, load_technicians, OrderItem
from .sheets import Record, append_record, get_all_records, get_user_mapping, set_user_mapping

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

(
    SEGMENT,
    ORDER_QUERY,
    ORDER_PICK,
    SERVICE_NUMBER,
    WO_NUMBER,
    TICKET_ID,
    DATE_OPEN,
    DATE_CLOSE,
    TECH1_UNIT,
    TECH1_NAME,
    TECH2_DECIDE,
    TECH2_UNIT,
    TECH2_NAME,
    WORKZONE,
    KETERANGAN,
    CONFIRM,
    SETME_UNIT,
    SETME_NAME,
) = range(18)

PAGE_SIZE = 10
DATE_FMT = "%d-%m-%Y %H:%M:%S"
LEGACY_DATE_FMT = "%Y-%m-%d %H:%M:%S"
DATE_INPUT_HINT = "DD-MM-YYYY HH:MM:SS"
BTN_BACK = "⬅️ Back"
BTN_CANCEL = "❌ Cancel"
BTN_SKIP = "⏭️ Skip"

TOTAL_STEPS = 12


def _step_text(step: int, title: str, instruction: str = "") -> str:
    message = f"🧭 Step {step}/{TOTAL_STEPS} — {title}"
    if instruction:
        message += f"\n{instruction}"
    return message

def _tz_now(tz_name: str) -> datetime:
    return datetime.now(ZoneInfo(tz_name))


def _parse_date(value: str) -> datetime | None:
    text = value.strip()
    for fmt in (DATE_FMT, LEGACY_DATE_FMT):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _fmt_order_item(item: OrderItem) -> str:
    return f"{item.name} (bobot {item.weight})"


def _field_nav_keyboard(include_skip: bool = False) -> ReplyKeyboardMarkup:
    rows = [[BTN_BACK, BTN_CANCEL]]
    if include_skip:
        rows.insert(0, [BTN_SKIP])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=False)


def _is_cancel(text: str) -> bool:
    return text.strip() == BTN_CANCEL


def _is_back(text: str) -> bool:
    return text.strip() == BTN_BACK


def _segment_keyboard(segments: List[str]) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text=s, callback_data=f"SEG|{s}")] for s in segments]
    return InlineKeyboardMarkup(buttons)


def _order_page_keyboard(segment: str, items: List[OrderItem], page: int) -> InlineKeyboardMarkup:
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_items = items[start:end]
    buttons = []
    for item in page_items:
        buttons.append([
            InlineKeyboardButton(
                text=item.name[:45],
                callback_data=f"ORDSEL|{segment}|{item.id}",
            )
        ])
    nav = []
    if start > 0:
        nav.append(InlineKeyboardButton("Prev", callback_data=f"ORDPAGE|{segment}|{page-1}"))
    if end < len(items):
        nav.append(InlineKeyboardButton("Next", callback_data=f"ORDPAGE|{segment}|{page+1}"))
    if nav:
        buttons.append(nav)
    return InlineKeyboardMarkup(buttons)
    for idx in page_items:
        t = techs[idx]
        buttons.append([
            InlineKeyboardButton(text=t.name, callback_data=f"TECHSEL|{key}|{idx}")
        ])
    nav = []
    if start > 0:
        nav.append(InlineKeyboardButton("Prev", callback_data=f"TECHPAGE|{key}|{page-1}"))
    if end < len(tech_indices):
        nav.append(InlineKeyboardButton("Next", callback_data=f"TECHPAGE|{key}|{page+1}"))
    if nav:
        buttons.append(nav)
    return InlineKeyboardMarkup(buttons)


def _get_order_by_id(orders_by_segment: Dict[str, List[OrderItem]], segment: str, item_id: str) -> OrderItem | None:
    for item in orders_by_segment.get(segment, []):
        if item.id == item_id:
            return item
    return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    segments = sorted(context.bot_data["orders"].keys())
    await update.message.reply_text(
        _step_text(1, "Pilih Segment", "Silakan pilih segment pekerjaan dari tombol di bawah."),
        reply_markup=_segment_keyboard(segments),
    )
    return SEGMENT


async def segment_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    segment = query.data.split("|", 1)[1]
    context.user_data["segment"] = segment
    await query.edit_message_text(
        _step_text(2, "Pilih Jenis Order", "Bisa ketik kata kunci (contoh: Corrective) atau pilih dari daftar."),
        parse_mode=ParseMode.MARKDOWN,
    )
    items = context.bot_data["orders"][segment]
    await query.message.reply_text(
        f"Total jenis order: {len(items)}. Halaman 1:",
        reply_markup=_order_page_keyboard(segment, items, page=0),
    )
    return ORDER_QUERY


async def order_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, segment, page_str = query.data.split("|", 2)
    items = context.bot_data["orders"][segment]
    page = int(page_str)
    await query.edit_message_reply_markup(reply_markup=_order_page_keyboard(segment, items, page))
    return ORDER_QUERY


async def order_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, segment, item_id = query.data.split("|", 2)
    item = _get_order_by_id(context.bot_data["orders"], segment, item_id)
    if not item:
        await query.edit_message_text("Jenis order tidak ditemukan. Coba lagi.")
        return ORDER_QUERY
    context.user_data["order"] = item
    await query.edit_message_text(f"Terpilih: {_fmt_order_item(item)}")
    await query.message.reply_text(
        _step_text(3, "Service Number", "Isi No Inet / Voice / Site sesuai tiket."),
        reply_markup=_field_nav_keyboard(),
    )
    return SERVICE_NUMBER


async def order_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().lower()
    segment = context.user_data.get("segment")
    items = context.bot_data["orders"].get(segment, [])
    matches = [item for item in items if text in item.name.lower()]
    if not matches:
        await update.message.reply_text("Tidak ditemukan. Coba kata kunci lain atau pilih dari daftar.")
        return ORDER_QUERY
    if len(matches) == 1:
        item = matches[0]
        context.user_data["order"] = item
        await update.message.reply_text(f"Terpilih: {_fmt_order_item(item)}")
        await update.message.reply_text(
            _step_text(3, "Service Number", "Isi No Inet / Voice / Site sesuai tiket."),
            reply_markup=_field_nav_keyboard(),
        )
        return SERVICE_NUMBER

    if len(matches) > PAGE_SIZE:
        await update.message.reply_text("Hasil terlalu banyak. Persempit kata kunci.")
        return ORDER_QUERY

    buttons = [
        [InlineKeyboardButton(text=m.name[:45], callback_data=f"ORDSEL|{segment}|{m.id}")]
        for m in matches
    ]
    await update.message.reply_text("Pilih salah satu:", reply_markup=InlineKeyboardMarkup(buttons))
    return ORDER_QUERY


async def service_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if _is_cancel(text):
        await update.message.reply_text("Dibatalkan.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    if _is_back(text):
        segment = context.user_data.get("segment")
        if not segment:
            await update.message.reply_text("Segment belum dipilih. Jalankan /start lagi.", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        items = context.bot_data["orders"][segment]
        await update.message.reply_text(
            "Kembali ke pemilihan jenis order. Pilih dari daftar:",
            reply_markup=ReplyKeyboardRemove(),
        )
        await update.message.reply_text(
            f"Total jenis order: {len(items)}. Halaman 1:",
            reply_markup=_order_page_keyboard(segment, items, page=0),
        )
        return ORDER_QUERY
    context.user_data["service_number"] = text
    await update.message.reply_text(_step_text(4, "WO Number", "Isi nomor SC/WO."), reply_markup=_field_nav_keyboard())
    return WO_NUMBER


async def wo_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if _is_cancel(text):
        await update.message.reply_text("Dibatalkan.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    if _is_back(text):
        await update.message.reply_text(
            _step_text(3, "Service Number", "Isi No Inet / Voice / Site sesuai tiket."),
            reply_markup=_field_nav_keyboard(),
        )
        return SERVICE_NUMBER
    context.user_data["wo_number"] = text
    await update.message.reply_text(_step_text(5, "Ticket ID", "Isi nomor tiket gangguan/provisioning."), reply_markup=_field_nav_keyboard())
    return TICKET_ID


async def ticket_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if _is_cancel(text):
        await update.message.reply_text("Dibatalkan.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    if _is_back(text):
        await update.message.reply_text(_step_text(4, "WO Number", "Isi nomor SC/WO."), reply_markup=_field_nav_keyboard())
        return WO_NUMBER
    context.user_data["ticket_id"] = text
    await update.message.reply_text(_step_text(6, "Tanggal Open", f"Format: {DATE_INPUT_HINT}"), reply_markup=_field_nav_keyboard())
    return DATE_OPEN


async def date_open(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if _is_cancel(text):
        await update.message.reply_text("Dibatalkan.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    if _is_back(text):
        await update.message.reply_text(_step_text(5, "Ticket ID", "Isi nomor tiket gangguan/provisioning."), reply_markup=_field_nav_keyboard())
        return TICKET_ID
    if not _parse_date(text):
        await update.message.reply_text(f"Format salah. Gunakan {DATE_INPUT_HINT}", reply_markup=_field_nav_keyboard())
        return DATE_OPEN
    context.user_data["tanggal_open"] = text
    await update.message.reply_text(_step_text(7, "Tanggal Close", f"Format: {DATE_INPUT_HINT}"), reply_markup=_field_nav_keyboard())
    return DATE_CLOSE


async def date_close(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if _is_cancel(text):
        await update.message.reply_text("Dibatalkan.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    if _is_back(text):
        await update.message.reply_text(_step_text(6, "Tanggal Open", f"Format: {DATE_INPUT_HINT}"), reply_markup=_field_nav_keyboard())
        return DATE_OPEN
    if not _parse_date(text):
        await update.message.reply_text(f"Format salah. Gunakan {DATE_INPUT_HINT}", reply_markup=_field_nav_keyboard())
        return DATE_CLOSE
    context.user_data["tanggal_close"] = text
    units = context.bot_data["units"]
    await update.message.reply_text("✅ Data tanggal tersimpan. Lanjut pilih teknisi via tombol di bawah.", reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text(_step_text(8, "Teknisi 1 - Pilih Unit", "Pilih unit terlebih dahulu."), reply_markup=_unit_keyboard(units, 0, "t1"))
    return TECH1_UNIT


async def unit_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, key, page_str = query.data.split("|", 2)
    units = context.bot_data["units"]
    page = int(page_str)
    await query.edit_message_reply_markup(reply_markup=_unit_keyboard(units, page, key))
    return TECH1_UNIT if key == "t1" else TECH2_UNIT


async def unit_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, key, unit = query.data.split("|", 2)
    techs = context.bot_data["techs"]
    indices = [i for i, t in enumerate(techs) if t.unit == unit]
    context.user_data[f"{key}_unit"] = unit
    context.user_data[f"{key}_tech_indices"] = indices
    await query.edit_message_text(f"Unit terpilih: {unit}")
    await query.message.reply_text(
        _step_text(8, "Teknisi - Pilih Nama", f"Unit: {unit}"),
        reply_markup=_tech_keyboard(indices, techs, 0, key),
    )
    return TECH1_NAME if key == "t1" else TECH2_NAME


async def tech_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, key, page_str = query.data.split("|", 2)
    indices = context.user_data.get(f"{key}_tech_indices", [])
    techs = context.bot_data["techs"]
    page = int(page_str)
    await query.edit_message_reply_markup(reply_markup=_tech_keyboard(indices, techs, page, key))
    return TECH1_NAME if key == "t1" else TECH2_NAME


async def tech_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, key, idx_str = query.data.split("|", 2)
    techs = context.bot_data["techs"]
    tech = techs[int(idx_str)]
    context.user_data[f"{key}_name"] = tech.name
    await query.edit_message_text(f"Teknisi dipilih: {tech.name}")

    if key == "t1":
        buttons = [
            [InlineKeyboardButton("Tidak ada Teknisi 2", callback_data="T2NONE")],
            [InlineKeyboardButton("Pilih Teknisi 2", callback_data="T2PICK")],
        ]
        await query.message.reply_text(_step_text(9, "Teknisi 2 (Opsional)", "Pilih jika ada teknisi pendamping."), reply_markup=InlineKeyboardMarkup(buttons))
        return TECH2_DECIDE

    await query.message.reply_text(_step_text(10, "Workzone", "Isi area/workzone pekerjaan."), reply_markup=_field_nav_keyboard())
    return WORKZONE


async def tech2_decide(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "T2NONE":
        context.user_data["t2_name"] = ""
        await query.edit_message_text("Teknisi 2: -")
        await query.message.reply_text(_step_text(10, "Workzone", "Isi area/workzone pekerjaan."), reply_markup=_field_nav_keyboard())
        return WORKZONE

    units = context.bot_data["units"]
    await query.edit_message_text(_step_text(9, "Teknisi 2 - Pilih Unit", "Pilih unit teknisi kedua."))
    await query.message.reply_text(_step_text(9, "Teknisi 2 - Pilih Unit", "Pilih salah satu unit di bawah."), reply_markup=_unit_keyboard(units, 0, "t2"))
    return TECH2_UNIT


async def workzone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if _is_cancel(text):
        await update.message.reply_text("Dibatalkan.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    if _is_back(text):
        await update.message.reply_text("Kembali ke langkah Teknisi 2.", reply_markup=ReplyKeyboardRemove())
        if context.user_data.get("t2_name", None) == "":
            buttons = [
                [InlineKeyboardButton("Tidak ada Teknisi 2", callback_data="T2NONE")],
                [InlineKeyboardButton("Pilih Teknisi 2", callback_data="T2PICK")],
            ]
            await update.message.reply_text(_step_text(9, "Teknisi 2 (Opsional)", "Pilih jika ada teknisi pendamping."), reply_markup=InlineKeyboardMarkup(buttons))
            return TECH2_DECIDE
        units = context.bot_data["units"]
        await update.message.reply_text(_step_text(9, "Teknisi 2 - Pilih Unit", "Pilih unit teknisi kedua."), reply_markup=_unit_keyboard(units, 0, "t2"))
        return TECH2_UNIT
    context.user_data["workzone"] = text
    await update.message.reply_text(_step_text(11, "Keterangan", "Isi catatan tambahan, atau tekan ⏭️ Skip."), reply_markup=_field_nav_keyboard(include_skip=True))
    return KETERANGAN


async def keterangan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if _is_cancel(text):
        await update.message.reply_text("Dibatalkan.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    if _is_back(text):
        await update.message.reply_text(_step_text(10, "Workzone", "Isi area/workzone pekerjaan."), reply_markup=_field_nav_keyboard())
        return WORKZONE
    if text == BTN_SKIP:
        context.user_data["keterangan"] = ""
        await update.message.reply_text("Keterangan dilewati.", reply_markup=ReplyKeyboardRemove())
        return await _confirm(update, context)
    context.user_data["keterangan"] = text
    await update.message.reply_text("Siap, menampilkan konfirmasi...", reply_markup=ReplyKeyboardRemove())
    return await _confirm(update, context)


async def skip_keterangan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["keterangan"] = ""
    await update.message.reply_text("Keterangan dilewati.", reply_markup=ReplyKeyboardRemove())
    return await _confirm(update, context)


async def _confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    item: OrderItem = context.user_data["order"]
    summary = (
        "🧭 Step 12/12 — Konfirmasi Data\n\n*Konfirmasi data:*\n"
        f"Segment: {context.user_data['segment']}\n"
        f"Jenis Order: {item.name}\n"
        f"Bobot: {item.weight}\n"
        f"Service Number: {context.user_data['service_number']}\n"
        f"WO Number: {context.user_data['wo_number']}\n"
        f"Ticket ID: {context.user_data['ticket_id']}\n"
        f"Tanggal Open: {context.user_data['tanggal_open']}\n"
        f"Tanggal Close: {context.user_data['tanggal_close']}\n"
        f"Teknisi 1: {context.user_data['t1_name']}\n"
        f"Teknisi 2: {context.user_data.get('t2_name', '') or '-'}\n"
        f"Workzone: {context.user_data['workzone']}\n"
        f"Keterangan: {context.user_data.get('keterangan', '') or '-'}"
    )
    buttons = [
        [InlineKeyboardButton("Simpan", callback_data="SAVE")],
        [InlineKeyboardButton("Batal", callback_data="CANCEL")],
    ]
    await update.message.reply_text(summary, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(buttons))
    return CONFIRM

async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "CANCEL":
        await query.edit_message_text("Dibatalkan.")
        return ConversationHandler.END

    config = context.bot_data["config"]
    item: OrderItem = context.user_data["order"]
    user = query.from_user
    record = Record(
        timestamp=_tz_now(config.tz).isoformat(),
        submitter_user_id=str(user.id),
        submitter_username=user.username or "",
        segment=context.user_data["segment"],
        jenis_order=item.name,
        bobot=item.weight,
        service_number=context.user_data["service_number"],
        wo_number=context.user_data["wo_number"],
        ticket_id=context.user_data["ticket_id"],
        tanggal_open=context.user_data["tanggal_open"],
        tanggal_close=context.user_data["tanggal_close"],
        teknisi_1=context.user_data["t1_name"],
        teknisi_2=context.user_data.get("t2_name", ""),
        workzone=context.user_data["workzone"],
async def setme_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    techs = context.bot_data["techs"]
    tech = techs[int(idx_str)]
    user = query.from_user
    config = context.bot_data["config"]
    set_user_mapping(config, str(user.id), user.username or "", tech.name)
    await query.edit_message_text(f"Nama kamu tersimpan sebagai: {tech.name}")
    return ConversationHandler.END


def _compute_stats(records: List[dict], tech_name: str, now: datetime) -> Tuple[int, float, int, float]:
    today = now.date()
    month = now.month
    year = now.year

    today_count = 0
    today_points = 0.0
    month_count = 0
    month_points = 0.0

    for r in records:
        tech1 = (r.get("teknisi_1") or "").strip()
        tech2 = (r.get("teknisi_2") or "").strip()
        if tech_name not in (tech1, tech2):
            continue
        date_str = (r.get("tanggal_close") or "").strip()
        dt = _parse_date(date_str)
        if not dt:
            continue
        weight = float(r.get("bobot") or 0)
        if dt.date() == today:
            today_count += 1
            today_points += weight
        if dt.year == year and dt.month == month:
            month_count += 1
            month_points += weight

    return today_count, today_points, month_count, month_points


async def me(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config = context.bot_data["config"]
    user_id = str(update.message.from_user.id)
    tech_name = get_user_mapping(config, user_id)
    if not tech_name:
        await update.message.reply_text("Nama kamu belum diset. Jalankan /setme dulu.")
        return

    records = get_all_records(config)
    now = _tz_now(config.tz)
    tcount, tpoints, mcount, mpoints = _compute_stats(records, tech_name, now)

    await update.message.reply_text(
        f"Stats untuk {tech_name}\n"
        f"Hari ini ({now.strftime('%Y-%m-%d')}): {tcount} pekerjaan, {tpoints:.2f} poin\n"
        f"Bulan ini ({now.strftime('%Y-%m')}): {mcount} pekerjaan, {mpoints:.2f} poin"
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Gunakan: /stats Nama Teknisi")
        return
    tech_name = " ".join(context.args).strip()
    config = context.bot_data["config"]
    records = get_all_records(config)
    now = _tz_now(config.tz)
    tcount, tpoints, mcount, mpoints = _compute_stats(records, tech_name, now)
    await update.message.reply_text(
        f"Stats untuk {tech_name}\n"
        f"Hari ini ({now.strftime('%Y-%m-%d')}): {tcount} pekerjaan, {tpoints:.2f} poin\n"
        f"Bulan ini ({now.strftime('%Y-%m')}): {mcount} pekerjaan, {mpoints:.2f} poin"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = (
        "Panduan singkat alur input:\n"
        "- /start: input pekerjaan baru (step-by-step)\n"
        "- /setme: set nama teknisi kamu (sekali saja)\n"
        "- /me: lihat stats kamu hari ini & bulan ini\n"
        "- /stats Nama Teknisi: lihat stats teknisi tertentu\n"
        "- /cancel: batalkan proses input\n"
        "- /skip: lewati keterangan\n"
    )
    await update.message.reply_text(message)


def build_app() -> Application:
    config = load_config()
    orders = load_orders(config.data_dir)
    techs, units = load_technicians(config.data_dir)

    app = Application.builder().token(config.bot_token).build()
    app.bot_data["config"] = config
    app.bot_data["orders"] = orders
    app.bot_data["techs"] = techs
    app.bot_data["units"] = units

    conv_states = {
        SEGMENT: [CallbackQueryHandler(segment_chosen, pattern=r"^SEG\|")],
        ORDER_QUERY: [
            CallbackQueryHandler(order_selected, pattern=r"^ORDSEL\|"),
            CallbackQueryHandler(order_page, pattern=r"^ORDPAGE\|"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, order_query),
        ],
        SERVICE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, service_number)],
        WO_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, wo_number)],
        TICKET_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, ticket_id)],
        DATE_OPEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, date_open)],
        DATE_CLOSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, date_close)],
        TECH1_UNIT: [
            CallbackQueryHandler(unit_selected, pattern=r"^UNITSEL\|t1\|"),
            CallbackQueryHandler(unit_page, pattern=r"^UNITPAGE\|t1\|"),
        ],
        TECH1_NAME: [
            CallbackQueryHandler(tech_selected, pattern=r"^TECHSEL\|t1\|"),
            CallbackQueryHandler(tech_page, pattern=r"^TECHPAGE\|t1\|"),
        ],
        TECH2_DECIDE: [CallbackQueryHandler(tech2_decide, pattern=r"^(T2NONE|T2PICK)$")],
        TECH2_UNIT: [
            CallbackQueryHandler(unit_selected, pattern=r"^UNITSEL\|t2\|"),
            CallbackQueryHandler(unit_page, pattern=r"^UNITPAGE\|t2\|"),
        ],
        TECH2_NAME: [
            CallbackQueryHandler(tech_selected, pattern=r"^TECHSEL\|t2\|"),
            CallbackQueryHandler(tech_page, pattern=r"^TECHPAGE\|t2\|"),
        ],
        WORKZONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, workzone)],
        KETERANGAN: [
            CommandHandler("skip", skip_keterangan),
            MessageHandler(filters.TEXT & ~filters.COMMAND, keterangan),
        ],
        CONFIRM: [CallbackQueryHandler(confirm, pattern=r"^(SAVE|CANCEL)$")],
    }

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states=conv_states,
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    setme_states = {
        SETME_UNIT: [
            CallbackQueryHandler(setme_unit, pattern=r"^UNITSEL\|me\|"),
            CallbackQueryHandler(unit_page, pattern=r"^UNITPAGE\|me\|"),
        ],
        SETME_NAME: [
            CallbackQueryHandler(setme_name, pattern=r"^TECHSEL\|me\|"),
            CallbackQueryHandler(tech_page, pattern=r"^TECHPAGE\|me\|"),
        ],
    }

    setme_conv = ConversationHandler(
        entry_points=[CommandHandler("setme", setme)],
        states=setme_states,
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv)
    app.add_handler(setme_conv)
    app.add_handler(CommandHandler("me", me))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("help", help_command))

    return app


def main() -> None:
    app = build_app()
    app.run_polling()


if __name__ == "__main__":
    main()

