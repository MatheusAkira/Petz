"""Avaliação semântica com DeepEval + Ollama; notas consultivas de 0 a 1."""
import hashlib
import json
import math
import time
from datetime import datetime, timezone
from importlib.metadata import version
from petz.config import get_ollama_settings

RUBRIC_VERSION = 'deepeval-rag-1'
METRICS = {
    'faithfulness':'Fidelidade semântica',
    'correctness':'Correção factual',
    'completeness':'Completude',
    'relevance':'Relevância da resposta',
    'usefulness':'Utilidade',
}
ABSTENTIONS = {
    'sem evidência recuperada.', 'sem evidência acima do limiar.',
    'não encontrei informação suficiente na base. posso indicar atendimento humano.',
    'não sei responder com a base disponível. não encontrei política suficiente sobre esse tema. posso indicar atendimento humano.',
}


def standard_abstention(generation):
    answer = ' '.join(generation.get('answer','').casefold().split())
    return generation.get('supported') is False and answer in ABSTENTIONS


def build_metrics():
    # Importação adiada: modo offline não inicializa DeepEval.
    from .deepeval_backend import build_metrics as factory
    return factory()


def make_test_case(row,gold):
    from .deepeval_backend import make_test_case as factory
    return factory(row,gold)


def judge_rag_case(row,gold,generator_model=None):
    """Executa métricas separadas, mantendo notas parciais e erros auditáveis."""
    settings = get_ollama_settings()
    metadata = {'framework':'deepeval','model':settings.judge_model,
        'same_as_generator':settings.judge_model==(generator_model or settings.chat_model),
        'rubric_version':RUBRIC_VERSION,'evaluated_at':datetime.now(timezone.utc).isoformat()}
    if 'generation' not in row:
        return {**metadata,'status':'não executado','reason':'Não há resposta de geração validada para avaliar.'}
    start = time.perf_counter()
    try:
        metadata['framework_version'] = version('deepeval')
        test_case = make_test_case(row,gold)
        metrics = build_metrics()
    except Exception as error:
        return {**metadata,'status':'erro','reason':f'Não foi possível inicializar DeepEval: {type(error).__name__}: {error}',
                'latency_ms':round((time.perf_counter()-start)*1000,3)}
    scores = {key:None for key in METRICS}
    reasons,details,errors = {},{},{}
    for key in METRICS:
        metric = metrics[key]
        metric_start = time.perf_counter()
        if key == 'faithfulness' and (standard_abstention(row['generation']) or not row.get('hits')):
            reason = ('Abstenção padronizada sem afirmações factuais.' if standard_abstention(row['generation'])
                      else 'Não há contexto recuperado para medir fidelidade; consulte correção e abstenção.')
            reasons[key] = 'Não aplicável: '+reason
            details[key] = {'status':'não aplicável','metric':type(metric).__name__,'reason':reason}
            continue
        try:
            metric.measure(test_case,_show_indicator=False)
            score = metric.score
            if type(score) not in (int,float) or not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError('DeepEval retornou nota fora de 0–1.')
            if not isinstance(metric.reason,str) or not metric.reason.strip():
                raise ValueError('DeepEval não retornou justificativa.')
            scores[key] = float(score)
            reasons[key] = metric.reason
            details[key] = {'status':'avaliado','metric':type(metric).__name__,'score':float(score),'reason':metric.reason}
        except Exception as error:
            errors[key] = f'{type(error).__name__}: {error}'
            reasons[key] = 'Falha na avaliação: '+errors[key]
            details[key] = {'status':'erro','metric':type(metric).__name__,'reason':errors[key]}
        # Mantém os passos intermediários nativos para auditar notas inconsistentes.
        diagnostics = {}
        for attribute in ('claims','truths','statements','verdicts','evaluation_steps'):
            value = getattr(metric,attribute,None)
            if isinstance(value,list):
                diagnostics[attribute] = [item.model_dump(mode='json') if hasattr(item,'model_dump') else item for item in value]
        if diagnostics:
            details[key]['diagnostics'] = diagnostics
        details[key]['latency_ms'] = round((time.perf_counter()-metric_start)*1000,3)
    status = ('parcial' if any(value is not None for value in scores.values()) else 'erro') if errors else 'avaliado'
    return {**metadata,'status':status,'scores':scores,'reasons':reasons,'metric_results':details,'metric_errors':errors,
        'reason':'; '.join(f'{key}: {error}' for key,error in errors.items()),
        'reference_facts':gold['evidence'],'expected_output':test_case.expected_output,
        'reference_sha256':hashlib.sha256(json.dumps(gold,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
        'latency_ms':round((time.perf_counter()-start)*1000,3)}
