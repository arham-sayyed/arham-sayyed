import chess
import chess.svg
import json
import os
import re
import shutil
import sys
import urllib.parse
from datetime import datetime, timezone

GAME_FILE        = 'chess/game.json'
BOARD_FILE       = 'chess/board.svg'
LEADERBOARD_FILE = 'chess/leaderboard.json'
LEADERBOARD_MD   = 'leaderboard.md'
ARCHIVE_DIR      = 'chess/archive'
README           = 'README.md'
REPO             = 'arham-sayyed/arham-sayyed'

START = '<!-- CHESS_START -->'
END   = '<!-- CHESS_END -->'

COOLDOWN_SECONDS = 180

PIECE_EMOJI = {
    chess.PAWN:   '♙',
    chess.KNIGHT: '♘',
    chess.BISHOP: '♗',
    chess.ROOK:   '♖',
    chess.QUEEN:  '♕',
    chess.KING:   '♔',
}

PIECE_ORDER = ['♙', '♘', '♗', '♖', '♕', '♔']


def utc_now():
    return datetime.now(timezone.utc)


def utc_now_iso():
    return utc_now().isoformat()


def format_date(iso_str):
    dt = datetime.fromisoformat(iso_str)
    return f'{dt.day} {dt.strftime("%b %Y")}'


def load_game():
    with open(GAME_FILE, encoding='utf-8') as f:
        return json.load(f)


def save_game(game):
    with open(GAME_FILE, 'w', encoding='utf-8') as f:
        json.dump(game, f, indent=2)


def load_leaderboard():
    if not os.path.exists(LEADERBOARD_FILE):
        return []
    with open(LEADERBOARD_FILE, encoding='utf-8') as f:
        return json.load(f)


def save_leaderboard(entries):
    with open(LEADERBOARD_FILE, 'w', encoding='utf-8') as f:
        json.dump(entries, f, indent=2)


def cooldown_remaining(game, author):
    last_at = None
    for m in game.get('moves', []):
        if m.get('by') == author:
            last_at = m.get('at')
    if not last_at:
        return 0
    try:
        last_dt = datetime.fromisoformat(last_at)
    except ValueError:
        return 0
    elapsed = (utc_now() - last_dt).total_seconds()
    return max(0, int(COOLDOWN_SECONDS - elapsed))


def render_board(board):
    lastmove = board.peek() if board.move_stack else None
    svg = chess.svg.board(
        board,
        size=400,
        coordinates=True,
        lastmove=lastmove,
        colors={
            'square light':          '#f0d9b5',
            'square dark':           '#b58863',
            'square light lastmove': '#cdd16a',
            'square dark lastmove':  '#aaa23b',
            'margin':                '#1a1a2e',
            'coord':                 '#9b8fa4',
        }
    )
    with open(BOARD_FILE, 'w', encoding='utf-8') as f:
        f.write(svg)


def build_move_section(board):
    turn_label = 'White ♙' if board.turn == chess.WHITE else 'Black ♟'

    groups = {}
    for move in sorted(board.legal_moves, key=lambda m: board.san(m)):
        piece = board.piece_at(move.from_square)
        emoji = PIECE_EMOJI.get(piece.piece_type if piece else chess.PAWN, '♙')
        groups.setdefault(emoji, [])
        san     = board.san(move)
        uci     = move.uci()
        title   = urllib.parse.quote(f'chess: {uci}')
        url     = f'https://github.com/{REPO}/issues/new?title={title}&body=Playing+{uci}+%28{san}%29'
        groups[emoji].append(f'[{san}]({url})')

    reset_url = (
        f'https://github.com/{REPO}/issues/new'
        f'?title={urllib.parse.quote("chess: reset")}'
        f'&body=Resetting+the+board'
    )

    lines = [f'**{turn_label} to move** — click any move to play it:\n']
    for emoji in PIECE_ORDER:
        if emoji in groups:
            lines.append(' · '.join(groups[emoji]))
    lines.append(f'\n---\n[🔄 Reset board]({reset_url})')

    return '\n\n'.join(lines)


def update_readme(board, status):
    with open(README, encoding='utf-8') as f:
        content = f.read()

    if status != 'active':
        reset_url = (
            f'https://github.com/{REPO}/issues/new'
            f'?title={urllib.parse.quote("chess: reset")}'
            f'&body=Resetting+the+board'
        )
        inner = f'**Game over — {status}** 🏁\n\n[🔄 Start a new game]({reset_url})'
    else:
        inner = build_move_section(board)

    block = f'{START}\n\n{inner}\n\n{END}'
    updated = re.sub(
        rf'{re.escape(START)}.*?{re.escape(END)}',
        block,
        content,
        flags=re.DOTALL,
    )

    with open(README, 'w', encoding='utf-8') as f:
        f.write(updated)


def archive_game(game):
    entries = load_leaderboard()
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    n = len(entries) + 1
    archive_path = f'{ARCHIVE_DIR}/game-{n:03d}.svg'
    shutil.copyfile(BOARD_FILE, archive_path)
    entries.append({
        'started_at': game.get('started_at'),
        'ended_at':   utc_now_iso(),
        'status':     game['status'],
        'board_svg':  archive_path,
        'moves':      game.get('moves', []),
    })
    save_leaderboard(entries)


def roster_for_color(moves, white):
    seen = []
    for i, m in enumerate(moves):
        is_white_move = (i % 2 == 0)
        if is_white_move != white:
            continue
        by = m.get('by', 'unknown')
        if by not in seen:
            seen.append(by)
    return seen


def render_roster(usernames):
    if not usernames:
        return '*(no moves yet)*'
    return ' · '.join(f'`[{u}](https://github.com/{u})`' for u in usernames)


def status_label(status):
    if status == 'active':
        return 'In progress'
    if 'wins' in status:
        return f'🏆 {status}'
    return status


def render_game_block(started_at, ended_at, status, board_svg, moves):
    start_label = format_date(started_at) if started_at else '?'
    end_label = 'Ongoing' if status == 'active' else (format_date(ended_at) if ended_at else '?')
    white = roster_for_color(moves, True)
    black = roster_for_color(moves, False)
    lines = [
        f'## Game — {start_label} – {end_label}',
        f'**Status:** {status_label(status)}',
        '',
        f'![Board]({board_svg})',
        '',
        '**White** ♙',
        render_roster(white),
        '',
        '--- VS ---',
        '',
        '**Black** ♟',
        render_roster(black),
        '',
        '---',
    ]
    return '\n'.join(lines)


def update_leaderboard(game):
    entries = load_leaderboard()
    blocks = []

    if game['status'] == 'active':
        blocks.append(render_game_block(
            game.get('started_at'), None, 'active', BOARD_FILE, game.get('moves', [])
        ))

    for entry in reversed(entries):
        blocks.append(render_game_block(
            entry.get('started_at'), entry.get('ended_at'), entry['status'],
            entry['board_svg'], entry.get('moves', [])
        ))

    content = '# ♟️ Chess Leaderboard\n\n' + '\n\n'.join(blocks) + '\n'
    with open(LEADERBOARD_MD, 'w', encoding='utf-8') as f:
        f.write(content)


def main():
    if len(sys.argv) < 2:
        print('Usage: python chess/play.py <uci_move|reset> [author]')
        sys.exit(1)

    move_str = sys.argv[1].strip().lower()
    author   = sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2].strip() else 'unknown'
    game     = load_game()
    board    = chess.Board(game['fen'])

    if move_str == 'reset':
        if game.get('status', 'active') == 'active':
            print('Reset blocked: game still in progress')
            print('REASON:reset_blocked')
            sys.exit(1)

        board = chess.Board()
        game  = {'fen': board.fen(), 'moves': [], 'status': 'active', 'started_at': utc_now_iso()}
        save_game(game)
        render_board(board)
        update_readme(board, 'active')
        update_leaderboard(game)
        print('Board reset.')
        return

    remaining = cooldown_remaining(game, author)
    if remaining > 0:
        print(f'Cooldown: {author} must wait {remaining}s before playing again')
        print(f'REASON:cooldown:{remaining}')
        sys.exit(1)

    # Validate UCI format
    try:
        move = chess.Move.from_uci(move_str)
    except ValueError:
        print(f'Bad UCI format: {move_str}')
        print('REASON:bad_format')
        sys.exit(1)

    if move not in board.legal_moves:
        print(f'Illegal move: {move_str}')
        print('REASON:illegal')
        sys.exit(1)

    san = board.san(move)
    board.push(move)

    status = 'active'
    if board.is_checkmate():
        winner = 'White' if board.turn == chess.BLACK else 'Black'
        status = f'{winner} wins by checkmate'
    elif board.is_stalemate():
        status = 'Draw by stalemate'
    elif board.is_insufficient_material():
        status = 'Draw by insufficient material'
    elif board.is_fifty_moves():
        status = 'Draw by fifty-move rule'

    now = utc_now_iso()
    game['fen']    = board.fen()
    game['status'] = status
    game.setdefault('started_at', now)
    game.setdefault('moves', []).append({'uci': move_str, 'san': san, 'by': author, 'at': now})

    save_game(game)
    render_board(board)
    update_readme(board, status)

    if status != 'active':
        archive_game(game)

    update_leaderboard(game)

    print(f'Played: {san} ({move_str})')
    if status != 'active':
        print(f'Game over: {status}')


if __name__ == '__main__':
    main()
