"""Local, single-user paper registry. Run: python quantum.py --demo."""
import argparse
import json
import mimetypes
import sqlite3
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


class Library:
    def __init__(self, state):
        self.state = Path(state).resolve()
        self.state.mkdir(parents=True, exist_ok=True)
        self.db = self.state / 'registry.sqlite'
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS vaults(id TEXT PRIMARY KEY, name TEXT, root TEXT UNIQUE);
                CREATE TABLE IF NOT EXISTS papers(id TEXT PRIMARY KEY, vault TEXT, path TEXT, UNIQUE(vault,path));
                CREATE TABLE IF NOT EXISTS locations(paper TEXT, vault TEXT, folder TEXT,
                    UNIQUE(paper,vault,folder));
            ''')

    def connect(self):
        db = sqlite3.connect(self.db)
        db.row_factory = sqlite3.Row
        return db

    def resolve(self, vault, relative):
        with self.connect() as db:
            row = db.execute('SELECT root FROM vaults WHERE id=?', (vault,)).fetchone()
        if not row:
            raise ValueError('Unknown vault')
        root = Path(row['root']).resolve()
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise ValueError('Path must stay inside its vault')
        return path

    def add_vault(self, name, root):
        root = Path(root).resolve()
        if not root.is_dir():
            raise ValueError('Vault directory does not exist')
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO vaults VALUES(?,?,?)',
                       (str(uuid.uuid4()), name, str(root)))
            return db.execute('SELECT id FROM vaults WHERE root=?', (str(root),)).fetchone()['id']

    def register(self, vault, path):
        file = self.resolve(vault, path)
        if not file.is_file() or file.suffix.lower() != '.md':
            raise ValueError('Choose an existing Markdown paper')
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO papers VALUES(?,?,?)', (str(uuid.uuid4()), vault, path))
            return db.execute('SELECT id FROM papers WHERE vault=? AND path=?', (vault, path)).fetchone()['id']

    def paper(self, paper_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM papers WHERE id=?', (paper_id,)).fetchone()
        if not row:
            raise ValueError('Unknown paper')
        return dict(row)

    def show_here(self, paper, vault, folder):
        self.paper(paper)
        if not self.resolve(vault, folder).is_dir():
            raise ValueError('Destination folder does not exist')
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO locations VALUES(?,?,?)', (paper, vault, folder))

    def read(self, paper):
        row = self.paper(paper)
        return self.resolve(row['vault'], row['path']).read_text()

    def save(self, paper, content):
        row = self.paper(paper)
        self.resolve(row['vault'], row['path']).write_text(content)

    def move(self, paper, vault, folder):
        row = self.paper(paper)
        source = self.resolve(row['vault'], row['path'])
        destination_folder = self.resolve(vault, folder)
        if not destination_folder.is_dir():
            raise ValueError('Destination folder does not exist')
        target = destination_folder / source.name
        if target == source:
            return
        # Exclusive creation prevents overwriting an existing destination.
        with target.open('xb') as output:
            output.write(source.read_bytes())
        try:
            with self.connect() as db:
                db.execute('UPDATE papers SET vault=?,path=? WHERE id=?',
                           (vault, target.relative_to(self.resolve(vault, '')).as_posix(), paper))
        except Exception:
            target.unlink()
            raise
        source.unlink()

    def snapshot(self):
        with self.connect() as db:
            vaults = [dict(r) for r in db.execute('SELECT * FROM vaults')]
            papers = [dict(r) for r in db.execute('SELECT * FROM papers')]
            locations = [dict(r) for r in db.execute('SELECT * FROM locations')]
        for vault in vaults:
            root = Path(vault.pop('root'))
            vault['folders'] = [''] + sorted(p.relative_to(root).as_posix() for p in root.rglob('*')
                if p.is_dir() and not any(x.startswith('.') for x in p.relative_to(root).parts)
                and p.resolve().is_relative_to(root.resolve()))
        return dict(vaults=vaults, papers=papers, locations=locations)


def demo(library):
    for name in ['Research', 'Writing']:
        root = library.state / 'demo-vaults' / name
        (root / 'Papers').mkdir(parents=True, exist_ok=True)
        (root / 'Ideas').mkdir(exist_ok=True)
        library.add_vault(name, root)
    snapshot = library.snapshot()
    research, writing = [next(v['id'] for v in snapshot['vaults'] if v['name'] == n)
                         for n in ['Research', 'Writing']]
    if snapshot['papers']:
        return
    path = library.resolve(research, 'Papers/One paper.md')
    if not path.exists():
        path.write_text('# One paper, many places\n\nThis is one original Markdown file.\n\nEdit it from either vault.\n')
    paper = library.register(research, 'Papers/One paper.md')
    library.show_here(paper, writing, 'Ideas')
    note = library.resolve(writing, 'Papers/A linked note.md')
    if not note.exists():
        note.write_text(f'# A linked note\n\nRead [the shared paper](#paper={paper}).\n\nThis link uses its permanent ID and survives moves made here.\n')
    library.register(writing, 'Papers/A linked note.md')


def handler(library):
    web = Path(__file__).parent / 'web'

    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, data, content_type='application/json'):
            body = json.dumps(data).encode() if content_type == 'application/json' else data
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            try:
                if path == '/api/library':
                    return self.respond(200, library.snapshot())
                if path.startswith('/api/paper/'):
                    paper = path.rsplit('/', 1)[1]
                    return self.respond(200, dict(**library.paper(paper), content=library.read(paper)))
                file = web / ('index.html' if path == '/' else path.lstrip('/'))
                if not file.resolve().is_relative_to(web.resolve()) or not file.is_file():
                    return self.respond(404, {'error': 'Not found'})
                self.respond(200, file.read_bytes(), mimetypes.guess_type(file)[0] or 'text/plain')
            except (ValueError, OSError) as error:
                self.respond(400, {'error': str(error)})

        def do_POST(self):
            # Require same-origin JSON; no cross-origin write access.
            if self.headers.get('Origin') not in (None, 'http://' + self.headers.get('Host', '')):
                return self.respond(403, {'error': 'Origin rejected'})
            if self.headers.get('Content-Type') != 'application/json':
                return self.respond(415, {'error': 'JSON required'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if size < 0 or size > 2_000_000:
                    raise ValueError('Request too large')
                data = json.loads(self.rfile.read(size))
                action = urlparse(self.path).path
                if action == '/api/show':
                    library.show_here(data['paper'], data['vault'], data['folder'])
                elif action == '/api/move':
                    library.move(data['paper'], data['vault'], data['folder'])
                elif action == '/api/save':
                    library.save(data['paper'], data['content'])
                elif action == '/api/register':
                    return self.respond(200, {'id': library.register(data['vault'], data['path'])})
                else:
                    return self.respond(404, {'error': 'Not found'})
                self.respond(200, {'ok': True})
            except (ValueError, KeyError, OSError, sqlite3.Error) as error:
                self.respond(400, {'error': str(error)})
    return Handler


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', default=str(Path.home() / '.quantum-papers'))
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--demo', action='store_true')
    parser.add_argument('--vault', action='append', default=[], help='Existing vault directory; repeat for more vaults')
    args = parser.parse_args()
    library = Library(args.state)
    for root in args.vault:
        library.add_vault(Path(root).name, root)
    if args.demo:
        demo(library)
    print(f'Quantum Papers listening on port {args.port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), handler(library)).serve_forever()
