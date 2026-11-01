import argparse
from .assistant import Assistant

def main():
    parser = argparse.ArgumentParser(description='Pet Aurora — demonstração fictícia')
    parser.add_argument('--customer', choices=['cliente-1','cliente-2','cliente-3'], default='cliente-1', help='Identidade confiável de demonstração; não é autenticação de produção')
    parser.add_argument('--backend', choices=['ollama'],default='ollama')
    parser.add_argument('--date', default=None, help='Data ISO para reprodução dos exemplos')
    args = parser.parse_args()
    from datetime import date
    bot = Assistant(args.customer, date.fromisoformat(args.date) if args.date else None,args.backend)
    print('Pet Aurora. Digite sair para encerrar.')
    while True:
        try:
            message = input('Você: ').strip()
        except (EOFError,KeyboardInterrupt):
            break
        if message.lower() in {'sair','exit','quit'}: break
        if not message: continue
        reply = bot.ask(message)
        print('Assistente:',reply.text)
        if reply.sources: print('Fontes:',', '.join(reply.sources))

if __name__ == '__main__':
    main()
