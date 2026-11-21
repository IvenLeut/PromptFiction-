"""One local background job, persisted progress and recoverable result snapshots."""
import json
import threading
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from mvp.engine import run, data_dir, write_json


class Jobs:
    def __init__(self):
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='founderradar')
        self.lock=threading.RLock()
        self.future=None
        self.stop=threading.Event()
        self.state={'status':'idle','percent':0,'message':'Bereit'}
        path=data_dir()/'job.json'
        if path.exists():
            try:self.state=json.loads(path.read_text(encoding='utf-8'))
            except (ValueError,OSError):pass
        if self.state['status']=='running':
            self.state.update(status='interrupted',message='Vorheriger Lauf unterbrochen. Erneut starten, um gespeicherte Quellen weiterzuverwenden.')

    def update(self, **changes):
        with self.lock:
            self.state.update(changes)
            write_json(data_dir()/'job.json',self.state)

    def snapshot(self):
        with self.lock:return dict(self.state)

    def start(self, options):
        with self.lock:
            if self.future and not self.future.done():raise ValueError('Es läuft bereits eine Analyse.')
            self.stop.clear()
            self.update(status='running',percent=0,message='Analyse wird vorbereitet',error=None,result_id=None,
                        started_at=datetime.now(timezone.utc).isoformat(),options=options.model_dump(mode='json'))
            self.future=self.pool.submit(self._work,options)

    def _work(self, options):
        try:
            result=run(options,lambda percent,message:self.update(percent=percent,message=message),cancelled=self.stop.is_set)
            self.update(status='done',percent=100,message='Analyse abgeschlossen',result_id=result.id)
        except InterruptedError as ex:self.update(status='interrupted',message=str(ex))
        except Exception as ex:
            import logging
            logging.getLogger(__name__).exception('MVP analysis failed')
            self.update(status='failed',message='Analyse fehlgeschlagen; letzter erfolgreicher Lauf bleibt erhalten.',error=type(ex).__name__+': '+str(ex)[:400])

    def cancel(self):
        self.stop.set()
        self.update(message='Anhalten nach dem aktuellen Quellenabruf …')
