"""Wait for native completion; an RPC acknowledgment is never compaction evidence."""
import json
import queue
import subprocess
import threading
import time


def codex_completed(event, session):
    params = event.get('params',{})
    return (event.get('method')=='item/completed' and params.get('threadId')==session
            and params.get('item',{}).get('type')=='contextCompaction')


def claude_completed(events, session):
    return (any(e.get('type')=='system' and e.get('subtype')=='compact_boundary' and e.get('session_id')==session for e in events)
            and any(e.get('type')=='result' and e.get('subtype')=='success' and e.get('session_id')==session for e in events))


def codex(binary, session, folder, fixture, env):
    start = time.monotonic(); deadline = start+180; inbox=queue.Queue(); completed=False
    with (folder/'compaction.stdout').open('w') as out, (folder/'compaction.stderr').open('w') as err:
        process=subprocess.Popen([binary,'app-server'],cwd=fixture,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err,text=True)
        def reader():
            for line in process.stdout:
                out.write(line);out.flush()
                try: inbox.put(json.loads(line))
                except ValueError: inbox.put({'parse_error':True})
            inbox.put({'eof':True})
        thread=threading.Thread(target=reader,daemon=True);thread.start()
        def send(value):
            process.stdin.write(json.dumps(value)+'\n');process.stdin.flush()
        def receive():
            remaining=deadline-time.monotonic()
            if remaining<=0: raise TimeoutError('compaction completion timeout')
            event=inbox.get(timeout=remaining)
            if event.get('error') or event.get('parse_error') or event.get('eof'):
                raise ValueError('app-server failed before completed compaction')
            if event.get('method')=='error': raise ValueError('native compaction error')
            if 'method' in event and 'id' in event:
                send({'id':event['id'],'error':{'code':-32601,'message':'No additional authority granted by correctness harness'}})
            return event
        def rpc(number,method,params):
            send(dict(id=number,method=method,params=params))
            while True:
                event=receive()
                if event.get('id')==number: return event.get('result')
        try:
            rpc(1,'initialize',{'clientInfo':{'name':'lean-startup-correctness','version':'1'},'capabilities':{'experimentalApi':True}})
            send({'method':'initialized','params':{}})
            resumed=rpc(2,'thread/resume',{'threadId':session,'cwd':str(fixture),'model':'gpt-6-astra',
                'approvalPolicy':'never','sandbox':'workspace-write'})
            if resumed.get('thread',{}).get('id') != session: raise ValueError('resumed wrong native session')
            # Completion may arrive before the acknowledgment; observe every event.
            send(dict(id=3,method='thread/compact/start',params={'threadId':session}))
            while not completed:
                completed=codex_completed(receive(),session)
            result=dict(exit_code=0,status='completed',compaction_completed=True)
        except (ValueError,TimeoutError,queue.Empty,OSError) as error:
            result=dict(exit_code=1,status='failed',compaction_completed=False,error=str(error))
        finally:
            process.stdin.close()
            try: process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: process.kill();process.wait()
            thread.join(timeout=1);process.stdout.close()
    return dict(result,duration_seconds=round(time.monotonic()-start,3))
