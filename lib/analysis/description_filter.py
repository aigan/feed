import hashlib
import json
import re
import sqlite3

from youtube import Channel, Video


class DescriptionFilter:
    THRESHOLD = 3

    SEPARATOR_RE = re.compile(r'^[^a-zA-Z0-9]*$')
    LINK_RE = re.compile(r'https?://|@\w+')

    @classmethod
    def split_blocks(cls, text):
        raw = re.split(r'\n\n+', text)
        blocks = []
        for block in raw:
            lines = block.splitlines()
            lines = [l for l in lines if not cls.SEPARATOR_RE.match(l)]
            cleaned = '\n'.join(lines).strip()
            if cleaned:
                blocks.append(cleaned)
        return blocks

    @classmethod
    def has_links(cls, block):
        return bool(cls.LINK_RE.search(block))

    @classmethod
    def checksum(cls, block):
        return hashlib.sha256(block.encode('utf-8')).hexdigest()

    @classmethod
    def get_db(cls, channel_id):
        db_path = Channel.get_active_dir(channel_id) / "text-blocks.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS blocks (
                checksum TEXT NOT NULL,
                video_id TEXT NOT NULL,
                last_updated TEXT NOT NULL,
                PRIMARY KEY (video_id, checksum)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_checksum ON blocks(checksum)")
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
            if not cls.has_links(block):
                kept.append(block)
                continue
            cs = cls.checksum(block)
            count = db.execute(
                "SELECT 1 FROM blocks WHERE checksum = ? AND video_id != ? LIMIT 2",
                (cs, video_id)
            ).fetchall()
            if len(count) >= cls.THRESHOLD - 1:
                continue
            kept.append(block)

        db.close()
        return '\n\n'.join(kept)
