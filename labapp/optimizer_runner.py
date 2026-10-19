"""One autonomous optimization cycle; only independent tests can promote it."""
import json
import sys
import time
from labapp import store,optimizer,research_jobs,paper


def main(identifier):
    try:
        from labapp.optimizer_data import freeze
        from labapp.optimizer_evaluate import evaluate
        optimizer.update(identifier,'冻结 Gate 合约行情、标记价格、资金费率及可用成交复盘')
        incumbent=optimizer.active();folder=store.STATE/'optimizer/runs'/identifier
        if (folder/'proposal.json').exists():
            from labapp.optimizer_data import refresh_forward,verify
            proposal=json.loads((folder/'proposal.json').read_text());manifest=verify(folder)
            if incumbent['id']!=proposal['parent']:raise ValueError('基础版本已变化，过期候选不应用。')
            if not refresh_forward(identifier):
                optimizer.finish(identifier,'waiting_forward',{'params':proposal['params'],'wait_until':manifest['holdout_end']});return
            params=proposal['params']
            optimizer.update(identifier,'未来数据已到齐，自动执行独立比较')
            with store.connect() as db:db.execute('UPDATE optimizer_control SET consumed_until=max(consumed_until,?) WHERE id=1',(manifest['holdout_end'],))
            result,bundle=evaluate(identifier,params,incumbent)
            if result['passed']:
                optimizer.propose_version(identifier,params,bundle,result,manifest['holdout_end'],incumbent['id'])
                optimizer.finish(identifier,'accepted',result)
            else:optimizer.finish(identifier,'rejected',result)
            return
        folder,manifest,frame=freeze(identifier)
        state=optimizer.status()
        if manifest['holdout_start']<state['consumed_until']:
            optimizer.finish(identifier,'waiting_data',error='等待完整的新 7 天最终检验数据；不重复使用已检验窗口。');return
        optimizer.update(identifier,'TradingAgents + DeepSeek 自动复盘与候选 JSON')
        from labapp import ai_connection
        if ai_connection.status().get('verification_stale'):ai_connection.validate()
        research_id=research_jobs.create_optimization(identifier,manifest,frame,incumbent)
        deadline=time.monotonic()+250
        while time.monotonic()<deadline:
            with store.connect() as db:
                run=db.execute('SELECT cancel FROM optimizer_runs WHERE id=?',(identifier,)).fetchone()
                job=db.execute('SELECT * FROM research_jobs WHERE id=?',(research_id,)).fetchone()
            if run['cancel']:raise ValueError('自动优化已停止。')
            if job['state']=='completed':break
            if job['state'] not in ('queued','running'):raise ValueError('AI 复盘未完成，保留原策略；不自动重发本轮付费请求。')
            time.sleep(1)
        else:raise ValueError('AI 复盘等待超时。')
        params=optimizer.validate_params(json.loads(job['result'])['proposal'])
        if manifest.get('forward_only'):
            (folder/'proposal.json').write_text(json.dumps({'params':params,'parent':incumbent['id']}))
            from labapp import training
            try:training.enqueue('gate')
            except ValueError:pass # Existing training remains independent and is not interrupted.
            optimizer.finish(identifier,'waiting_forward',{'params':params,'wait_until':manifest['holdout_end']});return
        optimizer.update(identifier,'FreqAI 开发集训练及 Freqtrade 含成本样本外比较')
        with store.connect() as db:
            db.execute('UPDATE optimizer_control SET consumed_until=max(consumed_until,?) WHERE id=1',(manifest['holdout_end'],))
        result,bundle=evaluate(identifier,params,incumbent)
        # Each final-test window is spent exactly once, whether it passes or fails.
        if result['passed']:
            optimizer.propose_version(identifier,params,bundle,result,manifest['holdout_end'],incumbent['id'])
            optimizer.finish(identifier,'accepted',result)
        else:optimizer.finish(identifier,'rejected',result)
        store.event('optimizer','info','自动优化完成：'+('候选通过，等待空仓自动切换' if result['passed'] else '候选未通过，原版保留'))
    except Exception as exc:
        from labapp import training
        training.init();training.finish(identifier,'failed',error='自动优化本轮未完成，原模型保留。')
        optimizer.finish(identifier,'failed',error=str(exc)[:500] if isinstance(exc,ValueError) else '自动优化异常：'+type(exc).__name__+'；原策略保留，详情见本机日志。')
        raise


if __name__=='__main__':main(sys.argv[1])
