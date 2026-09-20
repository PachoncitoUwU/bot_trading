"""Trade Result Visual Card Generator for Telegram Broadcasts.

Generates beautiful, high-resolution dark-mode summary images of completed trades
with crystal-clear typography (Segoe UI / Arial) and 100% human-friendly metrics.
"""
import io
import os
from decimal import Decimal
from typing import Optional
from PIL import Image, ImageDraw, ImageFont


def _get_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Loads system TrueType font (Segoe UI or Arial) with safe fallback."""
    font_candidates = []
    if bold:
        font_candidates = [
            "C:/Windows/Fonts/seguisb.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]
    else:
        font_candidates = [
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]

    for path in font_candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def generate_trade_card_image(
    symbol: str,
    side: str,
    entry_price: Decimal,
    exit_price: Decimal,
    net_pnl: Decimal,
    pnl_pct: Decimal,
    pattern_name: str = "Estrategia IA",
    is_win: bool = True,
    invested_amount: Optional[Decimal] = None,
    account_equity: Optional[Decimal] = None,
) -> io.BytesIO:
    """
    Generates an ultra-clean, modern visual trading card as PNG bytes.
    Designed to be instantly readable on mobile Telegram.
    """
    width = 900
    height = 500

    # Fonts
    f_badge = _get_font(18, bold=True)
    f_title = _get_font(32, bold=True)
    f_subtitle = _get_font(20, bold=False)
    f_huge_number = _get_font(52, bold=True)
    f_label = _get_font(18, bold=False)
    f_val = _get_font(24, bold=True)
    f_footer = _get_font(18, bold=False)

    # Color Palette (Binance Pro Dark Theme)
    bg_main = (14, 17, 23)             # Deep obsidian background
    card_bg = (24, 29, 39)             # Container card surface
    border_color = (45, 55, 72)        # Elegant border
    box_bg = (32, 39, 52)              # Inner data boxes
    text_white = (255, 255, 255)
    text_muted = (148, 163, 184)

    # Status Colors
    accent_green = (16, 185, 129)      # Emerald Green
    accent_red = (239, 68, 68)         # Coral Red
    accent = accent_green if is_win else accent_red

    image = Image.new("RGB", (width, height), bg_main)
    draw = ImageDraw.Draw(image)

    # Outer Card Frame
    draw.rounded_rectangle([20, 20, width - 20, height - 20], radius=24, fill=card_bg, outline=border_color, width=2)

    # Top Status Bar
    draw.rounded_rectangle([20, 20, width - 20, 32], radius=6, fill=accent)

    # 1. Header: Status & Coin Name
    if is_win:
        header_text = "🎉 ¡OPERACIÓN GANADA CON ÉXITO!"
        explanation = "La IA detectó la subida, compró y aseguró tus ganancias automáticamente."
    else:
        header_text = "🛡️ PROTECCIÓN ACTIVADA (PÉRDIDA FRENADA)"
        explanation = "El mercado retrocedió, pero el bot frenó la pérdida para proteger tu capital."

    draw.text((45, 45), header_text, font=f_title, fill=accent)
    draw.text((45, 85), f"🪙 {symbol} • Modo Demo Binance (Precios en Vivo)", font=f_subtitle, fill=text_muted)

    # Pattern Badge on top right
    badge_text = f"🧠 {pattern_name[:24]}"
    draw.rounded_rectangle([width - 320, 48, width - 45, 92], radius=12, fill=box_bg, outline=accent, width=1)
    draw.text((width - 305, 58), badge_text, font=f_badge, fill=text_white)

    # 2. Main PnL Big Banner Box
    pnl_sign = "+" if net_pnl >= 0 else ""
    pnl_str = f"{pnl_sign}${net_pnl:,.2f} USDT  ({pnl_sign}{pnl_pct:.2f}%)"

    pnl_box_top = 125
    pnl_box_bottom = 230
    draw.rounded_rectangle([45, pnl_box_top, width - 45, pnl_box_bottom], radius=16, fill=box_bg, outline=border_color, width=1)

    draw.text((70, 140), "RESULTADO DE ESTA OPERACIÓN:", font=f_label, fill=text_muted)
    draw.text((70, 165), pnl_str, font=f_huge_number, fill=accent)

    # 3. Four Grid Metric Boxes
    # [Compró a]  [Vendió a]  [Inversión]  [Saldo Total]
    grid_y_top = 250
    grid_y_bottom = 350
    box_w = (width - 90 - 45) // 4  # ~175px each
    gap = 15

    box_data = [
        ("📥 Compró a:", f"${entry_price:,.2f}"),
        ("📤 Vendió a:", f"${exit_price:,.2f}"),
        ("💵 Inversión:", f"${invested_amount:,.2f}" if invested_amount else "Automática"),
        ("🏦 Saldo en Cuenta:", f"${account_equity:,.2f}" if account_equity else "Actualizado"),
    ]

    for idx, (lbl, val) in enumerate(box_data):
        bx_left = 45 + idx * (box_w + gap)
        bx_right = bx_left + box_w
        draw.rounded_rectangle([bx_left, grid_y_top, bx_right, grid_y_bottom], radius=12, fill=box_bg, outline=border_color, width=1)
        draw.text((bx_left + 14, grid_y_top + 18), lbl, font=f_label, fill=text_muted)
        draw.text((bx_left + 14, grid_y_top + 52), val, font=f_val, fill=text_white)

    # 4. Explanatory Note Box
    draw.rounded_rectangle([45, 370, width - 45, 425], radius=12, fill=(20, 24, 32), outline=border_color, width=1)
    draw.text((65, 388), f"💡 {explanation}", font=f_footer, fill=text_white)

    # 5. Footer Signature
    draw.text((45, 448), "🤖 Binance Trading Hub • Sistema 100% Autónomo con Gestión de Riesgo", font=f_footer, fill=text_muted)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", quality=95)
    buffer.seek(0)
    return buffer


def generate_entry_chart_card(
    symbol: str,
    side: str,  # "CALL" / "PUT"
    entry_price: Decimal,
    candles: list,
    duration_minutes: int = 1,
    pattern_name: str = "Estrategia IA",
    reason: str = "",
    stake: Optional[Decimal] = None,
    mode_label: str = "DEMO (IQ Option Práctica)",
) -> io.BytesIO:
    """
    Renders a high-resolution chart card showing recent Japanese candlesticks
    with a highlighted glowing arrow/indicator pointing to the exact entry point.
    """
    width = 920
    height = 540

    # Fonts
    f_title = _get_font(28, bold=True)
    f_subtitle = _get_font(18, bold=False)
    f_badge = _get_font(16, bold=True)
    f_label = _get_font(15, bold=False)
    f_val = _get_font(18, bold=True)
    f_footer = _get_font(14, bold=False)

    # Colors
    bg_main = (14, 17, 23)
    card_bg = (24, 29, 39)
    border_color = (45, 55, 72)
    chart_bg = (18, 22, 32)
    text_white = (255, 255, 255)
    text_muted = (148, 163, 184)

    is_call = side.upper() in ("CALL", "BUY")
    accent_color = (16, 185, 129) if is_call else (239, 68, 68)  # Green for CALL, Red for PUT
    direction_label = "CALL (SUBIDA 🟢)" if is_call else "PUT (BAJADA 🔴)"
    dur_str = f"{duration_minutes} Minuto" if duration_minutes == 1 else f"{duration_minutes} Minutos"

    image = Image.new("RGB", (width, height), bg_main)
    draw = ImageDraw.Draw(image)

    # Outer Card Frame
    draw.rounded_rectangle([15, 15, width - 15, height - 15], radius=20, fill=card_bg, outline=border_color, width=2)

    # Top Status Bar
    draw.rounded_rectangle([15, 15, width - 15, 26], radius=6, fill=accent_color)

    # 1. Header
    header_text = f"⚡ ORDEN ABIERTA: {direction_label}"
    draw.text((40, 40), header_text, font=f_title, fill=accent_color)
    draw.text((40, 76), f"🪙 {symbol} • {mode_label} • Expiración: {dur_str}", font=f_subtitle, fill=text_muted)

    # Pattern Badge top-right
    badge_text = f"🧠 {pattern_name[:26]}"
    draw.rounded_rectangle([width - 320, 42, width - 40, 82], radius=10, fill=(32, 39, 52), outline=accent_color, width=1)
    draw.text((width - 305, 52), badge_text, font=f_badge, fill=text_white)

    # 2. Chart Canvas Area
    c_left = 40
    c_top = 115
    c_right = width - 40
    c_bottom = 370
    c_width = c_right - c_left
    c_height = c_bottom - c_top

    draw.rounded_rectangle([c_left, c_top, c_right, c_bottom], radius=14, fill=chart_bg, outline=border_color, width=1)

    # Draw Candlesticks if available (exact 25 1-minute candles)
    recent_candles = candles[-25:] if candles and len(candles) >= 5 else []

    if recent_candles:
        # Extract min and max price for scaling
        all_highs = [float(c[2]) for c in recent_candles]
        all_lows = [float(c[3]) for c in recent_candles]
        min_p = min(all_lows)
        max_p = max(all_highs)
        p_padding = (max_p - min_p) * 0.15 or 1.0
        min_p -= p_padding
        max_p += p_padding
        p_range = max_p - min_p if (max_p - min_p) > 0 else 1.0

        def to_y(price_val):
            norm = (float(price_val) - min_p) / p_range
            return c_bottom - 20 - int(norm * (c_height - 40))

        # Horizontal grid lines
        for i in range(1, 4):
            gy = c_top + int(c_height * (i / 4.0))
            draw.line([(c_left + 10, gy), (c_right - 60, gy)], fill=(30, 38, 54), width=1)
            p_val = max_p - (p_range * (i / 4.0))
            draw.text((c_right - 55, gy - 8), f"${p_val:,.2f}" if p_val >= 10 else f"{p_val:.4f}", font=f_footer, fill=text_muted)

        # Draw 25 candles
        num_c = len(recent_candles)
        candle_w = max(6, int((c_width - 80) / num_c) - 4)
        step = int((c_width - 80) / num_c)

        for i, c in enumerate(recent_candles):
            cx = c_left + 25 + i * step + candle_w // 2
            o_y = to_y(c[1])
            h_y = to_y(c[2])
            l_y = to_y(c[3])
            cl_y = to_y(c[4])

            is_green = float(c[4]) >= float(c[1])
            c_color = (16, 185, 129) if is_green else (239, 68, 68)

            # Wick
            draw.line([(cx, h_y), (cx, l_y)], fill=c_color, width=1)

            # Body
            b_top = min(o_y, cl_y)
            b_bottom = max(o_y, cl_y)
            if b_bottom - b_top < 2:
                b_bottom = b_top + 2
            draw.rectangle([cx - candle_w // 2, b_top, cx + candle_w // 2, b_bottom], fill=c_color)

        # Highlight Entry Point on the last candle
        last_cx = c_left + 25 + (num_c - 1) * step + candle_w // 2
        entry_y = to_y(entry_price)

        # Horizontal dashed entry guide line
        for dash_x in range(c_left + 10, c_right - 60, 10):
            draw.line([(dash_x, entry_y), (dash_x + 5, entry_y)], fill=accent_color, width=1)

        # Glowing Bullseye Target Marker at exact entry point
        draw.ellipse([last_cx - 10, entry_y - 10, last_cx + 10, entry_y + 10], outline=accent_color, width=2)
        draw.ellipse([last_cx - 4, entry_y - 4, last_cx + 4, entry_y + 4], fill=text_white)

        # Marker Arrow Badge with Pointer Triangle
        arrow_box_w = 185
        arrow_box_h = 34
        ab_x1 = max(c_left + 15, last_cx - arrow_box_w // 2)
        ab_x2 = min(c_right - 15, ab_x1 + arrow_box_w)

        entry_p_str = f"${float(entry_price):,.2f}" if float(entry_price) >= 10 else f"{float(entry_price):.5f}"
        if is_call:
            # CALL: Box positioned below candle, arrow pointing UP to target
            ab_y1 = min(c_bottom - arrow_box_h - 10, entry_y + 22)
            ab_y2 = ab_y1 + arrow_box_h
            # Pointer triangle
            draw.polygon([(last_cx, entry_y + 8), (last_cx - 8, ab_y1), (last_cx + 8, ab_y1)], fill=(16, 185, 129))
            draw.rounded_rectangle([ab_x1, ab_y1, ab_x2, ab_y2], radius=8, fill=(16, 185, 129), outline=text_white, width=1)
            draw.text((ab_x1 + 12, ab_y1 + 8), f"🟢 ENTRADA CALL: {entry_p_str}", font=f_badge, fill=(0, 0, 0))
        else:
            # PUT: Box positioned above candle, arrow pointing DOWN to target
            ab_y1 = max(c_top + 10, entry_y - arrow_box_h - 22)
            ab_y2 = ab_y1 + arrow_box_h
            # Pointer triangle
            draw.polygon([(last_cx, entry_y - 8), (last_cx - 8, ab_y2), (last_cx + 8, ab_y2)], fill=(239, 68, 68))
            draw.rounded_rectangle([ab_x1, ab_y1, ab_x2, ab_y2], radius=8, fill=(239, 68, 68), outline=text_white, width=1)
            draw.text((ab_x1 + 12, ab_y1 + 8), f"🔴 ENTRADA PUT: {entry_p_str}", font=f_badge, fill=text_white)
    else:
        entry_p_str = f"${float(entry_price):,.2f}" if float(entry_price) >= 10 else f"{float(entry_price):.5f}"
        draw.text((c_left + 40, c_top + 100), f"Entrada detectada a {entry_p_str} en {symbol}", font=f_subtitle, fill=text_white)

    # 3. Bottom Summary Info Grid
    # [Inversión] [Precio Entrada] [Expiración] [Razón Técnica de la IA]
    b_top = 385
    b_bottom = 475

    col1_w = 150
    col2_w = 160
    col3_w = 140
    col4_w = width - 80 - col1_w - col2_w - col3_w - 30

    # Box 1: Stake
    draw.rounded_rectangle([40, b_top, 40 + col1_w, b_bottom], radius=12, fill=(32, 39, 52), outline=border_color, width=1)
    draw.text((52, b_top + 14), "💵 Inversión:", font=f_label, fill=text_muted)
    stake_text = f"${float(stake):,.2f} USD" if stake else "$10.00 USD"
    draw.text((52, b_top + 45), stake_text, font=f_val, fill=text_white)

    # Box 2: Entry Price
    bx2 = 40 + col1_w + 10
    draw.rounded_rectangle([bx2, b_top, bx2 + col2_w, b_bottom], radius=12, fill=(32, 39, 52), outline=border_color, width=1)
    draw.text((bx2 + 14, b_top + 14), "📥 Precio Entrada:", font=f_label, fill=text_muted)
    draw.text((bx2 + 14, b_top + 45), entry_p_str, font=f_val, fill=accent_color)

    # Box 3: Expiration
    bx3 = bx2 + col2_w + 10
    draw.rounded_rectangle([bx3, b_top, bx3 + col3_w, b_bottom], radius=12, fill=(32, 39, 52), outline=border_color, width=1)
    draw.text((bx3 + 14, b_top + 14), "⏱️ Expiración:", font=f_label, fill=text_muted)
    dur_str = f"{duration_minutes} Minuto" if duration_minutes == 1 else f"{duration_minutes} Minutos"
    draw.text((bx3 + 14, b_top + 45), dur_str, font=f_val, fill=(0, 240, 255))

    # Box 4: Reason
    bx4 = bx3 + col3_w + 10
    draw.rounded_rectangle([bx4, b_top, width - 40, b_bottom], radius=12, fill=(20, 25, 36), outline=border_color, width=1)
    draw.text((bx4 + 14, b_top + 14), "🧠 Razón Técnica IA:", font=f_label, fill=text_muted)
    short_reason = reason[:58] + ("..." if len(reason) > 58 else "")
    draw.text((bx4 + 14, b_top + 45), f"💡 {short_reason}", font=f_footer, fill=text_white)

    # 4. Footer
    draw.text((40, 498), f"🤖 Trading Bot IA Pro • Operación de {dur_str} en tiempo real", font=f_footer, fill=text_muted)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", quality=95)
    buffer.seek(0)
    return buffer


def generate_result_chart_card(
    symbol: str,
    side: str,
    entry_price: Decimal,
    exit_price: Decimal,
    net_pnl: Decimal,
    pnl_pct: Decimal,
    candles: list,
    duration_minutes: int = 1,
    pattern_name: str = "Estrategia IA",
    is_win: bool = True,
    stake: Optional[Decimal] = None,
    account_equity: Optional[Decimal] = None,
    mode_label: str = "DEMO (IQ Option Práctica)",
) -> io.BytesIO:
    """
    Renders an ultra-clean, high-resolution result card with the completed candlestick chart,
    showing both the entry level and exit closing level, plus outcome badge (WIN / LOSS).
    """
    width = 920
    height = 560

    # Fonts
    f_title = _get_font(28, bold=True)
    f_subtitle = _get_font(18, bold=False)
    f_badge = _get_font(16, bold=True)
    f_label = _get_font(15, bold=False)
    f_val = _get_font(18, bold=True)
    f_huge = _get_font(38, bold=True)
    f_footer = _get_font(14, bold=False)

    # Colors
    bg_main = (14, 17, 23)
    card_bg = (24, 29, 39)
    border_color = (45, 55, 72)
    chart_bg = (18, 22, 32)
    text_white = (255, 255, 255)
    text_muted = (148, 163, 184)

    accent_color = (16, 185, 129) if is_win else (239, 68, 68)
    status_title = "🏆 ¡OPERACIÓN GANADA!" if is_win else "🛑 PROTECCIÓN CERRADA"
    dir_label = "CALL (SUBIDA 🟢)" if side.upper() in ("CALL", "BUY") else "PUT (BAJADA 🔴)"
    dur_str = f"{duration_minutes} Minuto" if duration_minutes == 1 else f"{duration_minutes} Minutos"

    image = Image.new("RGB", (width, height), bg_main)
    draw = ImageDraw.Draw(image)

    # Outer Card Frame
    draw.rounded_rectangle([15, 15, width - 15, height - 15], radius=20, fill=card_bg, outline=border_color, width=2)

    # Top Status Bar
    draw.rounded_rectangle([15, 15, width - 15, 26], radius=6, fill=accent_color)

    # 1. Header
    draw.text((40, 38), status_title, font=f_title, fill=accent_color)
    draw.text((40, 74), f"🪙 {symbol} • {dir_label} • Duración: {dur_str} • {mode_label}", font=f_subtitle, fill=text_muted)

    # PnL Banner Badge on Top Right
    pnl_sign = "+" if net_pnl >= 0 else ""
    pnl_str = f"{pnl_sign}${float(net_pnl):,.2f} USD ({pnl_sign}{float(pnl_pct):.1f}%)"
    badge_w = 310
    draw.rounded_rectangle([width - badge_w - 40, 36, width - 40, 84], radius=12, fill=(32, 39, 52), outline=accent_color, width=2)
    draw.text((width - badge_w - 25, 47), pnl_str, font=f_badge, fill=accent_color)

    # 2. Chart Canvas Area
    c_left = 40
    c_top = 108
    c_right = width - 40
    c_bottom = 380
    c_width = c_right - c_left
    c_height = c_bottom - c_top

    draw.rounded_rectangle([c_left, c_top, c_right, c_bottom], radius=14, fill=chart_bg, outline=border_color, width=1)

    recent_candles = candles[-25:] if candles and len(candles) >= 5 else []
    if recent_candles:
        all_highs = [float(c[2]) for c in recent_candles]
        all_lows = [float(c[3]) for c in recent_candles]
        all_highs.extend([float(entry_price), float(exit_price)])
        all_lows.extend([float(entry_price), float(exit_price)])
        min_p = min(all_lows)
        max_p = max(all_highs)
        p_padding = (max_p - min_p) * 0.15 or 1.0
        min_p -= p_padding
        max_p += p_padding
        p_range = max_p - min_p if (max_p - min_p) > 0 else 1.0

        def to_y(price_val):
            norm = (float(price_val) - min_p) / p_range
            return c_bottom - 20 - int(norm * (c_height - 40))

        # Horizontal grid lines
        for i in range(1, 4):
            gy = c_top + int(c_height * (i / 4.0))
            draw.line([(c_left + 10, gy), (c_right - 60, gy)], fill=(30, 38, 54), width=1)
            p_val = max_p - (p_range * (i / 4.0))
            draw.text((c_right - 55, gy - 8), f"${p_val:,.2f}" if p_val >= 10 else f"{p_val:.4f}", font=f_footer, fill=text_muted)

        # Draw 25 candles
        num_c = len(recent_candles)
        candle_w = max(6, int((c_width - 80) / num_c) - 4)
        step = int((c_width - 80) / num_c)

        for i, c in enumerate(recent_candles):
            cx = c_left + 25 + i * step + candle_w // 2
            o_y = to_y(c[1])
            h_y = to_y(c[2])
            l_y = to_y(c[3])
            cl_y = to_y(c[4])

            is_green = float(c[4]) >= float(c[1])
            c_color = (16, 185, 129) if is_green else (239, 68, 68)

            draw.line([(cx, h_y), (cx, l_y)], fill=c_color, width=1)
            b_top = min(o_y, cl_y)
            b_bottom = max(o_y, cl_y)
            if b_bottom - b_top < 2:
                b_bottom = b_top + 2
            draw.rectangle([cx - candle_w // 2, b_top, cx + candle_w // 2, b_bottom], fill=c_color)

        # Entry Price Line (Cyan dashed)
        entry_y = to_y(entry_price)
        for dash_x in range(c_left + 10, c_right - 70, 10):
            draw.line([(dash_x, entry_y), (dash_x + 5, entry_y)], fill=(0, 240, 255), width=1)
        entry_p_str = f"${float(entry_price):,.2f}" if float(entry_price) >= 10 else f"{float(entry_price):.5f}"
        draw.text((c_left + 15, max(c_top + 8, entry_y - 18)), f"Entrada: {entry_p_str}", font=f_footer, fill=(0, 240, 255))

        # Exit Price Line (Accent dashed)
        exit_y = to_y(exit_price)
        for dash_x in range(c_left + 10, c_right - 70, 10):
            draw.line([(dash_x, exit_y), (dash_x + 5, exit_y)], fill=accent_color, width=2)
        exit_p_str = f"${float(exit_price):,.2f}" if float(exit_price) >= 10 else f"{float(exit_price):.5f}"
        draw.text((c_left + 15, max(c_top + 8, exit_y + 4)), f"Cierre: {exit_p_str}", font=f_footer, fill=accent_color)

        # Final Outcome Indicator on last candle
        last_cx = c_left + 25 + (num_c - 1) * step + candle_w // 2
        draw.ellipse([last_cx - 10, exit_y - 10, last_cx + 10, exit_y + 10], outline=accent_color, width=3)
        draw.ellipse([last_cx - 4, exit_y - 4, last_cx + 4, exit_y + 4], fill=text_white)
    else:
        entry_p_str = f"${float(entry_price):,.2f}" if float(entry_price) >= 10 else f"{float(entry_price):.5f}"
        exit_p_str = f"${float(exit_price):,.2f}" if float(exit_price) >= 10 else f"{float(exit_price):.5f}"
        draw.text((c_left + 40, c_top + 100), f"Resultado: Entrada {entry_p_str} -> Cierre {exit_p_str}", font=f_subtitle, fill=text_white)

    # 3. Bottom Summary Info Grid
    # [Inversión] [Duración] [Resultado Neto] [Saldo en Cuenta]
    b_top = 398
    b_bottom = 490

    box_w = (width - 80 - 30) // 4  # 4 equal boxes
    gap = 10

    boxes = [
        ("💵 Inversión:", f"${float(stake):,.2f} USD" if stake else "$10.00 USD", text_white),
        ("⏱️ Duración:", dur_str, (0, 240, 255)),
        ("💰 Resultado:", pnl_str, accent_color),
        ("🏦 Saldo Actual:", f"${float(account_equity):,.2f} USD" if account_equity else "Actualizado", (16, 185, 129)),
    ]

    for idx, (lbl, val, col) in enumerate(boxes):
        bx1 = 40 + idx * (box_w + gap)
        bx2 = bx1 + box_w
        draw.rounded_rectangle([bx1, b_top, bx2, b_bottom], radius=12, fill=(32, 39, 52), outline=border_color, width=1)
        draw.text((bx1 + 14, b_top + 14), lbl, font=f_label, fill=text_muted)
        draw.text((bx1 + 14, b_top + 45), val, font=f_val, fill=col)

    # 4. Footer
    draw.text((40, 515), "🤖 Trading Bot IA Pro • Sistema de Aprendizaje Reforzado con Gestión de Capital", font=f_footer, fill=text_muted)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", quality=95)
    buffer.seek(0)
    return buffer


