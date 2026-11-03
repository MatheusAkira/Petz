import csv
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from uuid import uuid4
from urllib.error import HTTPError

from kit.api_mock import OrderAPI, Session
from .retrieval import ROOT, Chunk, Retriever, RetrievalError, norm
from .rules import cancellable, free_shipping, return_eligible

ABSTENTION_TEXT = 'Não sei responder com a base disponível. Não encontrei política suficiente sobre esse tema. Posso indicar atendimento humano.'

@dataclass
class Reply:
    text: str
    route: str
    sources: list = field(default_factory=list)
    data: dict = field(default_factory=dict)

class Assistant:
    # Prepara uma sessão de atendimento: define o cliente e a data de referência,
    # configura a API de pedidos e o recuperador de políticas, carrega o catálogo
    # e inicia o contexto em memória e o caminho do arquivo de logs.
    def __init__(self, customer_id='cliente-1', today=None, backend='ollama', api=None, log_path=None):
        self.session = Session(customer_id)
        self.today = today or date.fromisoformat(os.getenv('PETZ_TODAY', date.today().isoformat()))
        if backend != 'ollama':
            raise ValueError('O único backend disponível é ollama.')
        self.backend = backend
        self.api = api or OrderAPI(fail=os.getenv('ORDERS_FAIL','0') == '1')
        self.retriever = Retriever()
        with (ROOT/'kit'/'catalogo.csv').open(encoding='utf-8', newline='') as f:
            self.products = list(csv.DictReader(f))
        self.context = {}
        self.log_path = Path(log_path) if log_path else ROOT/'logs'/'traces.jsonl'

    # Recebe uma mensagem e pede à LLM para identificar sua intenção.
    # Trata erros de conexão, timeout e formato, ou encaminha a intenção para
    # _respond. Ao final, registra rota, fontes, erros e latência, sem gravar
    # a mensagem original, e devolve um objeto Reply para a interface.
    def ask(self, message):
        started = time.perf_counter()
        planner = 'not_used'
        model_error = None
        if len(message) > 4000:
            reply = Reply('Envie uma mensagem de até 4000 caracteres.', 'limite')
        else:
            try:
                from .llm import plan, UnsafeToolArguments
                intent = plan(message, self.context)
            except UnsafeToolArguments:
                planner = 'rejected'
                model_error = 'unsafe_tool_arguments'
                reply = self._respond(message,'seguranca')
            except (OSError, ValueError, KeyError, TypeError) as error:
                planner = 'error'
                if isinstance(error,HTTPError):
                    model_error = f'http_{error.code}'
                    text = f'O Ollama retornou erro HTTP {error.code}. Confira o modelo configurado e sua disponibilidade.'
                elif isinstance(error,TimeoutError):
                    model_error = 'timeout'
                    text = 'O modelo demorou além do limite. Tente novamente ou aumente OLLAMA_TIMEOUT.'
                elif isinstance(error,OSError):
                    model_error = 'connection'
                    text = 'Não foi possível conectar ao Ollama. Verifique se o serviço está em execução e confira OLLAMA_URL.'
                else:
                    model_error = 'invalid_response'
                    text = 'O modelo respondeu em formato inválido para classificar a pergunta. Tente novamente; não foi um erro de conexão.'
                reply = Reply(text, 'erro_modelo')
            else:
                planner = 'ok'
                reply = self._respond(message, intent)
        event = {'trace_id':uuid4().hex,'route':reply.route,'sources':reply.sources,
                 'tool_status':reply.data.get('status_code'), 'backend':self.backend,
                 'planner':planner, 'model_error':model_error, 'latency_ms':round((time.perf_counter()-started)*1000,3)}
        event['rag'] = reply.data.get('rag')
        self.log_path.parent.mkdir(parents=True,exist_ok=True)
        with self.log_path.open('a',encoding='utf-8') as f:
            f.write(json.dumps(event,ensure_ascii=False)+'\n')
        return reply

    # Escolhe o fluxo de atendimento a partir da intenção identificada pela LLM.
    # Preserva a operação pendente quando o usuário informa apenas o número
    # solicitado e direciona perguntas para segurança, atendimento humano,
    # identidade, catálogo, produtos, pedidos, frete ou políticas.
    # Quando o assunto é desconhecido, responde com o texto de abstenção.
    def _respond(self, message, intent):
        t = norm(message)
        # Preencher um campo pedido não inicia uma nova operação de consulta.
        pending = self.context.get('pending')
        if self.context.get('awaiting_order_number') and pending in {'pedido','trocas','cancelamento'}:
            if re.fullmatch(r'\s*\d{4}\s*',message) and intent not in {'seguranca','saude','humano'}:
                intent = pending
            elif intent != pending:
                self.context.pop('awaiting_order_number',None)
                self.context.pop('pending',None)
        
        if intent == 'seguranca':
            return Reply('Não posso alterar regras, conceder cupons ou expor dados de outros clientes. Posso ajudar com as políticas e seus pedidos.', 'seguranca')
        if intent in {'saude','humano'}:
            intro = 'Não realizo diagnóstico nem prescrição. Procure um médico veterinário; em urgência, procure atendimento veterinário imediatamente. ' if intent == 'saude' else ''
            return Reply(intro+'Encaminhamento humano recomendado: atendimento@example.invalid, segunda a sexta, 9h às 18h (Brasília), exceto feriados. Canal fictício; nenhum chamado foi aberto.', 'escalacao', ['kit/politicas/atendimento.md'], {'reason':intent})
        if intent == 'outro_pedido':
            self.context.pop('order', None)
            self.context.pop('return_slots', None)
            self.context['pending'] = 'pedido'
            self.context['awaiting_order_number'] = True
            return Reply('Qual é o número do outro pedido?', 'pedir_numero')
        if intent in {'politica_trocas','politica_cancelamento'}:
            topic = intent.removeprefix('politica_')
            return self._policy_answer(message,topic)
        number = re.search(r'(?<!\d)(\d{4})(?!\d)', t)
        if intent == 'desconhecido':
            self.context.pop('pending',None)
            self.context.pop('awaiting_order_number',None)
            return Reply(ABSTENTION_TEXT, 'abstencao')
        self.context['intent'] = intent
        if intent == 'catalogo':
            return self._browse_catalog()
        if intent == 'produto':
            return self._recommend(message)
        if intent in {'pedido','cancelamento','trocas'}:
            return self._order_flow(intent,t,number)

        if intent == 'identidade':
            self.context.pop('pending', None)
            return Reply(
                'Sou o assistente virtual da Pet Aurora. '
                'Posso ajudar com pedidos, produtos e políticas da loja.',
                'identidade'
            )
        if intent == 'frete':
            return self._shipping(t)
        return self._policy_answer(message,intent)

    # Responde dúvidas sobre políticas usando RAG: recupera documentos pelo
    # retriever do LangChain, envia os trechos à geração e reúne as fontes
    # das citações validadas. Retorna abstenção quando faltam evidências
    # e uma mensagem de erro quando a recuperação ou a geração falha.
    def _policy_answer(self,message,intent):
        from .rag import generate_answer, GenerationError
        try:
            # A pergunta original é a consulta: não força o documento pelo nome da intenção.
            documents = self.retriever.as_langchain_retriever().invoke(message,config={'run_name':'policy_retrieval','callbacks':[]})
            chunks = [Chunk(d.metadata['chunk_id'],d.metadata['source'],d.metadata['title'],d.page_content,d.metadata['score']) for d in documents]
        except RetrievalError as error:
            return Reply(str(error),'erro_rag',data={'rag':{'stage':'retrieval','status':'error'}})
        metrics = {'stage':'retrieval','status':'ok','chunks':[{'id':c.id,'score':c.score} for c in chunks]}
        if not chunks:
            return Reply(ABSTENTION_TEXT,'abstencao',data={'rag':metrics})
        try:
            generated = generate_answer(message,chunks)
        except GenerationError:
            return Reply('Não consegui gerar uma resposta com fontes verificáveis. Tente novamente ou procure atendimento humano.','erro_rag',data={'rag':{**metrics,'stage':'generation','status':'error'}})
        if not generated['supported']:
            return Reply(ABSTENTION_TEXT,'abstencao',data={'rag':{**metrics,'supported':False}})
        by_id = {c.id:c for c in chunks}
        sources = sorted({by_id[c['chunk_id']].source for c in generated['citations']})
        return Reply(generated['answer'],intent,sources,{'rag':{**metrics,'stage':'generation','supported':True},'citations':generated['citations']})

    # Conduz consultas, cancelamentos e devoluções de um pedido.
    # Solicita ou reutiliza o número e consulta a API, que verifica a titularidade.
    # Para devolução, reúne motivo e condição da embalagem e calcula a
    # elegibilidade pela data de entrega. Apenas orienta: não altera o pedido.
    # t é a mensagem normalizada; number é a correspondência da expressão regular.
    def _order_flow(self,intent,t,number):
        if number:
            self.context['order'] = number.group(1)
            self.context.pop('return_slots',None)
        order_number = self.context.get('order')
        self.context['pending'] = intent
        if not order_number:
            self.context['awaiting_order_number'] = True
            return Reply('Qual é o número do pedido?', 'pedir_numero')
        self.context.pop('awaiting_order_number',None)
        result = self.api.get_order(order_number,self.session)
        if result.status != 200:
            texts = {403:'Acesso recusado: não posso consultar pedido de outro cliente.',404:'Pedido não encontrado. Confira o número.',503:'Consulta de pedidos indisponível temporariamente. Tente novamente ou procure atendimento humano; não confirmei nenhuma alteração.'}
            return Reply(texts[result.status], 'erro_pedido',data={'status_code':result.status})
        order = result.data
        base = {'status_code':200,'order':order_number,'status':order['status']}
        if intent == 'pedido':
            return Reply(f"Pedido {order_number}: {order['status']}. Pagamento: {order['pagamento']}. Nenhuma alteração foi executada.", 'pedido', data=base)
        if intent == 'cancelamento':
            eligible = cancellable(order['status'])
            text = 'Pode solicitar cancelamento ao atendimento, pois ainda não foi enviado.' if eligible else ('O pedido já está cancelado.' if order['status'] == 'Cancelado' else 'Não é permitido cancelar após Enviado. Siga o fluxo de devolução da RN01.')
            return Reply(text+' Esta consulta não executa cancelamento.', intent,['kit/politicas/cancelamento.md'],{**base,'eligible':eligible})
        if not order['entregue_em']:
            return Reply('Não há entrega registrada para calcular o prazo de devolução. Consulte o atendimento.', intent,['kit/politicas/trocas.md'],base)
        slots = self.context.setdefault('return_slots',{})
        if 'defeito' in t:
            slots['reason'] = 'defeito'
        elif any(x in t for x in ['arrepend','desisti','nao gostei']):
            slots['reason'] = 'arrependimento'
        if 'fechada' in t or 'lacrada' in t or 'nao esta aberta' in t:
            slots['opened'] = False
        elif 'aberta' in t or 'aberto' in t:
            slots['opened'] = True
        if len(order['itens']) != 1:
            return Reply('Informe o item do pedido que deseja devolver.', 'pedir_item')
        product = next(p for p in self.products if p['SKU'] == order['itens'][0]['sku'])
        if 'reason' not in slots:
            return Reply('A devolução é por arrependimento ou defeito?', 'pedir_motivo')
        if 'opened' not in slots and product['categoria'] in {'racao','areia'}:
            return Reply('A embalagem está aberta ou fechada?', 'pedir_embalagem')
        eligible = return_eligible(date.fromisoformat(order['entregue_em']),self.today,slots['reason'],product['categoria'],slots.get('opened',False))
        self.context.pop('pending',None)
        text = 'Elegível para solicitar devolução pela RN01.' if eligible else 'Não elegível pela RN01, considerando prazo, motivo e embalagem.'
        return Reply(text+' A solicitação depende do atendimento; nenhuma troca foi executada.',intent,['kit/politicas/trocas.md'],{**base,'eligible':eligible, 'days':(self.today-date.fromisoformat(order['entregue_em'])).days})

    # Extrai região e subtotal da mensagem normalizada e preserva esses dados
    # entre turnos. Com os dois campos, calcula o frete grátis pela RN03;
    # sem eles, consulta a política via RAG e pede os dados necessários.
    # Não calcula o valor do frete pago nem executa uma compra.
    def _shipping(self,t):
        regions = {'sudeste':'Sudeste','sul':'Sul','nordeste':'Nordeste','norte':'Norte','centro-oeste':'Centro-Oeste','centro oeste':'Centro-Oeste'}
        region = next((v for k,v in regions.items() if k in t),None)
        amounts = re.findall(r'(?:r\$\s*)?(\d+(?:[.,]\d{3})*[.,]\d{2}|\d+)',t)
        amount = None
        if amounts:
            raw = amounts[-1]
            amount = raw.replace('.','').replace(',','.') if ',' in raw else raw
        slots = self.context.setdefault('shipping',{})
        if region: slots['region'] = region
        if amount: slots['amount'] = amount
        self.context['pending'] = 'frete'
        source = ['kit/politicas/frete.md']
        if not {'region','amount'} <= slots.keys():
            reply = self._policy_answer(t,'frete')
            if reply.route == 'frete': reply.text += ' Informe o subtotal e a região para calcular.'
            return reply
        eligible = free_shipping(slots['amount'],slots['region'])
        return Reply('Frete grátis pela RN03.' if eligible else 'Sem frete grátis pela RN03. Consulte o custo no checkout.', 'frete',source,{'eligible':eligible,**slots})

    # Mostra uma visão geral do catálogo e encerra os filtros da busca anterior.
    # Lista categorias com estoque e até cinco exemplos reais, escolhendo um
    # por categoria. Depois pergunta a categoria ou a espécie desejada.
    def _browse_catalog(self):
        self.context['product'] = {}
        self.context.pop('product_needs_query',None)
        self.context['pending'] = 'produto'
        available = [p for p in self.products if int(p['estoque']) > 0]
        if not available:
            return Reply('Não há produtos disponíveis em estoque no momento.','catalogo',['kit/catalogo.csv'],{'skus':[]})
        labels = {'racao':'ração','areia':'areia','brinquedo':'brinquedos','acessorio':'acessórios','higiene':'higiene'}
        categories = sorted({labels.get(p['categoria'],p['categoria']) for p in available})
        # Amostra variada: um item real por categoria, sem presumir espécie.
        examples = []
        seen = set()
        for p in sorted(available,key=lambda p:float(p['preco'])):
            if p['categoria'] not in seen:
                seen.add(p['categoria'])
                examples.append(p)
        text = 'Temos estas categorias disponíveis: '+', '.join(categories)+'. Alguns exemplos:\n'
        text += '\n'.join(f"{p['SKU']} — {p['nome']} — R$ {p['preco'].replace('.',',')}" for p in examples[:5])
        text += '\nVocê procura alguma categoria específica? É para cão ou gato?'
        return Reply(text,'catalogo',['kit/catalogo.csv'],{'skus':[p['SKU'] for p in examples[:5]],'categories':categories})

    # Pede à LLM os filtros de produto e combina as informações com o contexto.
    # Preserva nome, tema ou SKU entre turnos; só remove essa restrição quando
    # há aceitação de alternativas ou uma nova busca indicada pela extração.
    # Confere o nome no catálogo e filtra espécie, categoria, orçamento e estoque.
    # Retorna até três itens pelo menor preço, sem inventar SKUs, e pede
    # esclarecimentos quando faltam dados ou a extração não é válida.
    def _recommend(self,message):
        from .catalog import extract_product_query, ProductQueryError
        try:
            extracted = extract_product_query(message,self.context.get('product',{}))
        except ProductQueryError as error:
            self.context['product_needs_query'] = True
            self.context['pending'] = 'produto'
            return Reply(str(error),'erro_produto')
        if self.context.get('product_needs_query') and extracted['query'] is None and not extracted['new_search']:
            return Reply('Preciso confirmar o nome ou tema do produto antes de recomendar. Qual produto você procura?','pedir_produto')
        self.context.pop('product_needs_query',None)
        slots = dict(self.context.get('product',{}))
        if extracted['new_search']:
            slots = {}
        was_waiting = slots.get('awaiting_alternatives',False)
        if slots.get('awaiting_alternatives') and extracted['alternatives'] == 'accept':
            slots.pop('query',None)
            slots.pop('awaiting_alternatives',None)
        for key in ['query','species','category','budget']:
            if extracted[key] is not None:
                slots[key] = extracted[key]
        self.context['product'] = slots
        self.context['pending'] = 'produto'
        candidates = self.products
        if slots.get('query'):
            terms = set(re.findall(r'[a-z0-9]+',norm(slots['query'])))
            candidates = [p for p in candidates if terms and terms <= set(re.findall(r'[a-z0-9]+',norm(p['SKU']+' '+p['nome']+' '+p['descricao'])))]
            if not candidates:
                slots['awaiting_alternatives'] = True
                text = f'Não encontrei produtos com o nome ou tema "{slots["query"]}" no catálogo.'
                if not (was_waiting and extracted['alternatives'] == 'reject'):
                    text += ' Quer que eu procure outras opções'+(' para '+('gato' if slots['species']=='gato' else 'cão') if 'species' in slots else '')+'?'
                return Reply(text,'produto',['kit/catalogo.csv'],{'skus':[],'filters':dict(slots)})
        slots.pop('awaiting_alternatives',None)
        if 'species' not in slots:
            return Reply('É para cão ou gato?', 'pedir_especie')
        items = [p for p in candidates if p['especie'] == slots['species'] and int(p['estoque']) > 0 and ('category' not in slots or p['categoria'] == slots['category']) and float(p['preco']) <= slots.get('budget',float('inf'))]
        items = sorted(items,key=lambda p:float(p['preco']))[:3]
        text = '\n'.join(f"{p['SKU']} — {p['nome']} — R$ {p['preco'].replace('.',',')} — estoque {p['estoque']}" for p in items) or 'Não encontrei produto disponível com esses filtros.'
        return Reply(text,'produto',['kit/catalogo.csv'],{'skus':[p['SKU'] for p in items], 'filters':dict(slots)})
