import hashlib
import json
import re
import sqlite3

from util import dump_json
from youtube import Channel, Video


class DescriptionFilter:
    """Strip description text that doesn't help classify a video's content.

    The goal is a description as short as possible that still distinguishes
    this video from others on the same channel.  Boilerplate like social
    links, merch plugs, membership calls-to-action, and channel-level
    hashtags are noise for classification and get removed."""

    @classmethod
    def get(cls, video):
        video_id = video.video_id
        channel_id = video.channel_id
        result_file = Video.get_processed_dir(video_id) / "description.txt"

        # Check if channel index needs updating by checking this video's freshness
        db = cls.get_db(channel_id)
        row = db.execute(
            "SELECT last_updated FROM blocks WHERE video_id = ? LIMIT 1",
            (video_id,)
        ).fetchone()
        db.close()

        if not row or row[0] < video.last_updated.isoformat():
            cls.index_channel(channel_id)

        # strip() will also re-index this specific video if stale
        description = cls.strip(video.description, video, channel_id)

        processed_dir = Video.get_processed_dir(video_id)
        processed_dir.mkdir(parents=True, exist_ok=True)
        result_file.write_text(description + '\n')

        # Write metadata + unique_length
        dump_json(processed_dir / "description.json", {
            "db_version": cls.DB_VERSION,
            "last_updated": video.last_updated.isoformat(),
            "unique_length": cls.unique_length(video.description, channel_id),
        })

        return description

    DB_VERSION = 6  # Bump to force full re-index of all channel text-blocks DBs

    THRESHOLD = 3

    SEPARATOR_RE = re.compile(r'^[^a-zA-Z0-9]*$')
    LINK_RE = re.compile(r'https?://|@\w+')
    URL_RE = re.compile(r'https?://\S+')
    TIMESTAMP_RE = re.compile(r'^\d{1,2}:\d{2}', re.MULTILINE)
    HASHTAG_LINE_RE = re.compile(r'^#\S+(\s+#\S+)*$')

    @classmethod
    def split_blocks(cls, text):
        lines = text.splitlines()

        # Above-the-fold: the first lines of a YouTube description are visible
        # without clicking "Show more" and often mix content with per-video
        # promos on adjacent lines.  When the first two lines are both short
        # (< 120 display chars, URLs counted as min(len, 20) since YouTube
        # shortens them), split them into separate blocks so the filter can
        # evaluate each independently.
        if len(lines) >= 2:
            first = lines[0].strip()
            second = lines[1].strip()
            if (first and second
                    and cls.display_length(first) < 120
                    and cls.display_length(second) < 120):
                lines = [lines[0], '', lines[1], ''] + lines[2:]

        # First pass: identify separator lines
        is_sep = [bool(line.strip() and cls.SEPARATOR_RE.match(line)) for line in lines]

        # Second pass: classify each separator as header-underline vs block-boundary.
        # A separator is a header-underline when:
        #   - Above (since previous separator or start): exactly 1 non-empty line, ≤60 chars
        #   - Below (until next separator or end): >1 non-empty line, or any line >60 chars
        is_boundary = list(is_sep)
        for i in range(len(lines)):
            if not is_sep[i]:
                continue

            above = []
            for j in range(i - 1, -1, -1):
                if is_sep[j]:
                    break
                if lines[j].strip():
                    above.append(lines[j].strip())

            below = []
            for j in range(i + 1, len(lines)):
                if is_sep[j]:
                    break
                if lines[j].strip():
                    below.append(lines[j].strip())

            if (len(above) == 1 and len(above[0]) <= 60 and
                    (len(below) > 1 or any(len(l) > 60 for l in below))):
                is_boundary[i] = False

        # Third pass: wrap only block-boundary separators with blank lines
        processed = []
        for i, line in enumerate(lines):
            if is_boundary[i]:
                processed.append('')
                processed.append(line)
                processed.append('')
            else:
                processed.append(line)

        # Fourth pass: hashtag-only lines become their own blocks so they
        # get indexed and go through commonality-based filtering.
        # Channel-level hashtags (#gaming #gamereviews) appear across many
        # videos and get stripped as boilerplate.  Video-specific hashtags
        # that appear in fewer than THRESHOLD videos are preserved.
        result = []
        for line in processed:
            if line.strip() and cls.HASHTAG_LINE_RE.match(line.strip()):
                result.append('')
                result.append(line)
                result.append('')
            else:
                result.append(line)
        processed = result

        text = '\n'.join(processed)

        raw = re.split(r'\n\n+', text)
        blocks = []
        for block in raw:
            cleaned = block.strip()
            if cleaned:
                blocks.append(cleaned)
        return blocks

    @classmethod
    def has_links(cls, block):
        return bool(cls.LINK_RE.search(block))

    @classmethod
    def has_timestamps(cls, block):
        return bool(cls.TIMESTAMP_RE.search(block))

    @classmethod
    def display_length(cls, line):
        """Line length with URLs counted as min(actual, 20) — YouTube shortens display URLs."""
        length = 0
        last_end = 0
        for m in cls.URL_RE.finditer(line):
            length += m.start() - last_end
            length += min(len(m.group()), 20)
            last_end = m.end()
        length += len(line) - last_end
        return length

    @classmethod
    def is_hashtag_block(cls, block):
        return bool(cls.HASHTAG_LINE_RE.match(block.strip()))

    @classmethod
    def clean_tags(cls, tags, channel_title):
        """Remove channel-identity tags. Tags matching the channel title
        (case-insensitive containment) are channel branding, not video content.
        We don't use cross-video commonality for tag filtering because tags
        legitimately repeat across series (e.g. game name in a Let's Play),
        and those are redundant with title+description anyway."""
        if not tags:
            return []
        title_lower = channel_title.lower()
        return [t for t in tags if t.lower() not in title_lower and title_lower not in t.lower()]

    @classmethod
    def checksum(cls, block):
        return hashlib.sha256(block.encode('utf-8')).hexdigest()

    @classmethod
    def get_db(cls, channel_id):
        db_path = Channel.get_active_dir(channel_id) / "text-blocks.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)

        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            try:
                row = conn.execute("SELECT value FROM meta WHERE key = 'version'").fetchone()
                if not row or int(row[0]) != cls.DB_VERSION:
                    conn.close()
                    db_path.unlink()
                else:
                    return conn
            except sqlite3.OperationalError:
                conn.close()
                db_path.unlink()

        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.execute("INSERT INTO meta (key, value) VALUES ('version', ?)", (str(cls.DB_VERSION),))
        conn.execute("""
            CREATE TABLE blocks (
                checksum TEXT NOT NULL,
                video_id TEXT NOT NULL,
                last_updated TEXT NOT NULL,
                PRIMARY KEY (video_id, checksum)
            )
        """)
        conn.execute("CREATE INDEX idx_checksum ON blocks(checksum)")
        conn.commit()
        return conn

    @classmethod
    def index_video(cls, db, video):
        video_id = video.video_id
        last_updated = video.last_updated.isoformat()

        row = db.execute(
            "SELECT last_updated FROM blocks WHERE video_id = ? LIMIT 1",
            (video_id,)
        ).fetchone()

        if row and row[0] == last_updated:
            return

        if row:
            db.execute("DELETE FROM blocks WHERE video_id = ?", (video_id,))

        blocks = cls.split_blocks(video.description)
        for block in blocks:
            cs = cls.checksum(block)
            db.execute(
                "INSERT OR IGNORE INTO blocks (checksum, video_id, last_updated) VALUES (?, ?, ?)",
                (cs, video_id, last_updated)
            )

    @classmethod
    def index_channel(cls, channel_id):
        db = cls.get_db(channel_id)

        indexed_ids = {
            row[0] for row in
            db.execute("SELECT DISTINCT video_id FROM blocks").fetchall()
        }

        uploads_dir = Channel.get_active_dir(channel_id) / "uploads"
        if not uploads_dir.exists():
            print("  No uploads directory")
            db.close()
            return

        all_video_ids = []
        for path in sorted(uploads_dir.glob('*.json')):
            data = json.loads(path.read_text())
            for video_id, _published_at in data:
                all_video_ids.append(video_id)

        new_ids = [vid for vid in all_video_ids if vid not in indexed_ids]
        if not new_ids:
            print(f"  All {len(all_video_ids)} videos already indexed")
            db.close()
            return

        print(f"  Indexing {len(new_ids)} new videos (of {len(all_video_ids)} total)")
        for i, video_id in enumerate(new_ids):
            try:
                video = Video.get(video_id)
                cls.index_video(db, video)
            except Exception as e:
                print(f"  Error indexing {video_id}: {e}")
            if (i + 1) % 1000 == 0:
                print(f"  Progress: {i + 1}/{len(new_ids)}")
                db.commit()

        db.commit()
        db.close()
        print("  Done")

    @classmethod
    def strip(cls, description, video, channel_id):
        db_path = Channel.get_active_dir(channel_id) / "text-blocks.db"
        if not db_path.exists():
            return description

        db = cls.get_db(channel_id)
        video_id = video.video_id
        last_updated = video.last_updated.isoformat()

        row = db.execute(
            "SELECT last_updated FROM blocks WHERE video_id = ? LIMIT 1",
            (video_id,)
        ).fetchone()

        if not row or row[0] != last_updated:
            cls.index_video(db, video)
            db.commit()

        blocks = cls.split_blocks(description)
        kept = []
        for block in blocks:
            if not cls.has_links(block) and not cls.is_hashtag_block(block):
                kept.append(block)
                continue
            if cls.has_timestamps(block):
                kept.append(block)
                continue
            cs = cls.checksum(block)
            count = db.execute(
                "SELECT 1 FROM blocks WHERE checksum = ? LIMIT 3",
                (cs,)
            ).fetchall()
            if len(count) >= cls.THRESHOLD:
                continue
            kept.append(block)

        # Merge adjacent separator blocks (keep first)
        cleaned = []
        for block in kept:
            is_sep = bool(cls.SEPARATOR_RE.match(block))
            if is_sep and cleaned and bool(cls.SEPARATOR_RE.match(cleaned[-1])):
                continue
            cleaned.append(block)

        # Strip leading/trailing separators
        while cleaned and cls.SEPARATOR_RE.match(cleaned[0]):
            cleaned.pop(0)
        while cleaned and cls.SEPARATOR_RE.match(cleaned[-1]):
            cleaned.pop()

        db.close()
        return '\n\n'.join(cleaned)

    @classmethod
    def unique_length(cls, description, channel_id):
        db_path = Channel.get_active_dir(channel_id) / "text-blocks.db"
        if not db_path.exists():
            return len(description)

        db = cls.get_db(channel_id)
        blocks = cls.split_blocks(description)
        kept = []
        for block in blocks:
            if cls.SEPARATOR_RE.match(block):
                continue
            cs = cls.checksum(block)
            count = db.execute(
                "SELECT 1 FROM blocks WHERE checksum = ? LIMIT 3",
                (cs,)
            ).fetchall()
            if len(count) >= cls.THRESHOLD:
                continue
            kept.append(block)
        db.close()

        text = re.sub(r'\n+', '\n', '\n'.join(kept))
        return len(text)
