import os
import re
import time
import requests
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from crewai.tools import tool
from sudoku import Sudoku
import pandas as pd
import PyPDF2
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import hashlib
from duckduckgo_search import DDGS

# ==========================================
# 1. ACESSO A ARQUIVOS LOCAIS (O mais básico)
# ==========================================
@tool("Local_TXT_Access")
def read_local_file(file_path: str) -> str:
    """
    Lê o conteúdo de um arquivo de texto local (.txt, .md, .csv).
    A entrada (input) deve ser o caminho completo ou relativo do arquivo.
    """
    try:
        if not os.path.exists(file_path):
            return f"Erro: O arquivo não foi encontrado em {file_path}"
        
        with open(file_path, 'r', encoding='utf-8') as f:
            conteudo = f.read()
        return conteudo
    except Exception as e:
        return f"Erro ao ler o arquivo: {str(e)}"

# ==========================================
# 2. XADREZ DIÁRIO (Com renderização de imagem)
# ==========================================
@tool("Lichess_Daily_Puzzle_API")
def fetch_chess_puzzle() -> str:
    """
    Busca o puzzle de xadrez diário do Lichess.
    Retorna a imagem do tabuleiro e a solução.
    """
    try:
        response = requests.get("https://lichess.org/api/puzzle/daily")
        response.raise_for_status()
        data = response.json()
        
        puzzle = data.get("puzzle", {})
        fen = puzzle.get('fen', '')
        
        # O Lichess tem um endpoint público que converte FEN em imagem
        fen_url = fen.replace(" ", "%20")
        img_url = f"https://lichess1.org/export/fen.gif?fen={fen_url}"
        
        resultado = (
            f"**Tabuleiro:**\n\n![Chess Board]({img_url})\n\n"
            f"**Rating:** {puzzle.get('rating')}\n"
            f"**Solução:** {puzzle.get('solution')}\n"
        )
        return resultado
    except Exception as e:
        return f"Erro ao buscar o puzzle de xadrez: {str(e)}"

# ==========================================
# 3. GERADOR DE SUDOKU LOCAL (Tabela Visual)
# ==========================================
@tool("Python_Sudoku_Generator")
def generate_sudoku(difficulty: float) -> str:
    """
    Gera um jogo de Sudoku formatado em uma tabela visual HTML.
    """
    try:
        # Trava a dificuldade em no máximo 0.85 para evitar loops longos
        difficulty = min(difficulty, 0.85)

        puzzle = Sudoku(3).difficulty(difficulty)
        tabuleiro_inicial = puzzle.board
        
        # Constrói uma tabela HTML limpa em vez de imprimir a lista bruta do Python
        tabela_html = '<table class="sudoku-board">\n'
        for row in tabuleiro_inicial:
            tabela_html += "  <tr>\n"
            for cell in row:
                valor = str(cell) if cell is not None else "&nbsp;"
                tabela_html += f"    <td>{valor}</td>\n"
            tabela_html += "  </tr>\n"
        tabela_html += "</table>"
        
        solucao = puzzle.solve().board
        # Mantemos a solução compacta para não ocupar muito espaço
        solucao_str = ", ".join(["".join(str(c) for c in row) for row in solucao[:3]]) + "..."
        
        return f"**Tabuleiro:**\n{tabela_html}\n\n**Solução do Auditor:**\n{solucao_str}"
    except Exception as e:
        return f"Erro ao gerar Sudoku: {str(e)}"

# ==========================================
# 4. PREVISÃO DO TEMPO (API com Autenticação)
# ==========================================
@tool("Fetch_Weather")
def fetch_weather(location: str) -> str:
    """
    Fetches daily weather summary and full 24-hour forecast tables.
    Saves greeting phrase and exact markdown tables to temporary files.
    """
    lat, lon = 50.1109, 8.7663 # Offenbach, Hessen, Germany
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,precipitation_probability,weathercode&daily=temperature_2m_max,temperature_2m_min,sunrise,sunset&timezone=Europe%2FBerlin"
    
    try:
        with requests.Session() as session:
            resp = session.get(url)
            resp.raise_for_status()
            data = resp.json()
        
        # --- 1. DATA E RESUMO DIÁRIO ---
        daily = data['daily']
        forecast_date_str = daily['time'][0] # Pega a data exata do relatório (ex: "2026-10-12")
        forecast_date = datetime.fromisoformat(forecast_date_str).date()
        
        max_temp = daily['temperature_2m_max'][0]
        min_temp = daily['temperature_2m_min'][0]
        sunrise_dt = datetime.fromisoformat(daily['sunrise'][0])
        sunset_dt = datetime.fromisoformat(daily['sunset'][0])
        
        dia_num = forecast_date.day
        sufixo = "th" if 11 <= dia_num <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(dia_num % 10, "th")
        data_extenso = forecast_date.strftime(f"{dia_num}{sufixo} of %B, %Y")
        
        summary_table = (
            "### Daily Summary\n\n"
            "| Date | Max Temp | Min Temp | Sunrise | Sunset |\n"
            "|:---:|:---:|:---:|:---:|:---:|\n"
            f"| {data_extenso} | {max_temp}°C | {min_temp}°C | {sunrise_dt.strftime('%H:%M')} | {sunset_dt.strftime('%H:%M')} |\n\n"
        )
        
        # --- 2. PREVISÃO HORA A HORA (TODAS AS 24 HORAS DO DIA) ---
        hourly = data['hourly']
        hourly_table = "### Hourly Forecast\n\n"
        hourly_table += "| Time | Temperature | Description | Probability of Rain |\n"
        hourly_table += "|:---:|:---:|:---:|:---:|\n"
        
        wmo_codes = {
            0: ("Clear sky", "☀️"), 1: ("Mainly clear", "🌤️"), 2: ("Partly cloudy", "⛅"), 3: ("Overcast", "☁️"),
            45: ("Fog", "🌫️"), 48: ("Depositing rime fog", "🌫️"),
            51: ("Light drizzle", "🌧️"), 53: ("Moderate drizzle", "🌧️"), 55: ("Dense drizzle", "🌧️"),
            61: ("Slight rain", "🌧️"), 63: ("Moderate rain", "🌧️"), 65: ("Heavy rain", "🌧️"),
            71: ("Slight snow", "❄️"), 73: ("Moderate snow", "❄️"), 75: ("Heavy snow", "❄️"),
            95: ("Thunderstorm", "⛈️")
        }
        
        noon_temp = None
        max_temp_time = "16:00"
        highest_hourly_temp = -999
        max_pop = 0
        
        for i in range(len(hourly['time'])):
            time_str = hourly['time'][i]
            dt = datetime.fromisoformat(time_str)
            
            # Valida estritamente contra a data do relatório da API
            if dt.date() == forecast_date:
                temp = hourly['temperature_2m'][i]
                pop = hourly['precipitation_probability'][i]
                code = hourly['weathercode'][i]
                
                if dt.hour == 12:
                    noon_temp = temp
                if temp > highest_hourly_temp:
                    highest_hourly_temp = temp
                    max_temp_time = dt.strftime('%H:%M')
                if pop > max_pop:
                    max_pop = pop
                    
                desc, emoji = wmo_codes.get(code, ("Unknown", "❓"))
                hourly_table += f"| {dt.strftime('%H:%M')} | {temp}°C | {emoji} {desc} | {pop}% |\n"
        
        # --- 3. FRASE PARA A SAUDAÇÃO ---
        noon_str = f"{noon_temp}°C at noon" if noon_temp is not None else f"{min_temp}°C"
        rain_str = "no expected rain" if max_pop < 20 else f"a {max_pop}% chance of rain"
        
        summary_sentence = (
            f"throughout the day, temperatures will range from {noon_str} "
            f"to a high of {highest_hourly_temp}°C by {max_temp_time}. "
            f"The sky will be mainly clear with {rain_str}."
        )
        
        combined_tables = summary_table + hourly_table
        
        # Salva diretamente em arquivos temporários
        Path('/tmp/weather_greeting.txt').write_text(summary_sentence, encoding='utf-8')
        Path('/tmp/weather_tables.txt').write_text(combined_tables, encoding='utf-8')
        
        return combined_tables
    except Exception as e:
        return f"Error fetching weather: {str(e)}"

# ==========================================
# 5. BUSCA NA INTERNET / NOTÍCIAS (DuckDuckGo News)
# ==========================================
@tool("Internet_Web_Search")
def search_internet(query: str) -> str:
    """
    Realiza buscas de notícias na internet com retry e controle de taxa para evitar Rate Limit.
    """
    # Pausa inicial de segurança entre chamadas de agentes
    time.sleep(2)
    
    for tentativa in range(3):
        try:
            with DDGS() as ddgs:
                # Tenta buscar via endpoint de notícias
                resultados = list(ddgs.news(query, max_results=3))
                
                # Se não encontrar em news, tenta o endpoint de texto geral
                if not resultados:
                    resultados = list(ddgs.text(query, max_results=3))
            
            if not resultados:
                return f"Nenhuma notícia recente encontrada para: {query}."

            texto_resposta = ""
            for item in resultados:
                titulo = item.get('title') or item.get('title')
                corpo = item.get('body') or item.get('snippet', '')
                url = item.get('url') or item.get('href', '')
                img = item.get('image', '')

                texto_resposta += f"- Título: {titulo}\n"
                texto_resposta += f"  Resumo: {corpo}\n"
                if img:
                    texto_resposta += f"  Imagem: {img}\n"
                texto_resposta += f"  Link: {url}\n\n"

            return texto_resposta

        except Exception as e:
            if "429" in str(e) or "Ratelimit" in str(e) or "Rate limit" in str(e):
                # Se for rate limit, espera 4 segundos antes da próxima tentativa
                time.sleep(4)
            else:
                time.sleep(2)
                
    return f"Não foi possível obter notícias para '{query}' devido a instabilidade temporária no provedor de buscas."

# ==========================================
# 6. LEITOR DO OBSIDIAN (Lógica de Datas e Pastas)
# ==========================================
@tool("Obsidian_24h_Reader")
def read_recent_obsidian_notes(pasta_obsidian: str) -> str:
    """
    Lê todos os arquivos Markdown (.md) de um diretório do Obsidian que foram
    criados ou modificados nas últimas 24 horas.
    A entrada deve ser o caminho absoluto da pasta do Obsidian.
    """
    try:
        caminho = Path(pasta_obsidian)
        if not caminho.exists() or not caminho.is_dir():
            return f"Erro: A pasta {pasta_obsidian} não existe ou não é um diretório válido."

        limite_tempo = datetime.now() - timedelta(hours=24)
        arquivos_recentes = []

        # Busca todos os .md iterando pelas subpastas (rglob)
        for arquivo in caminho.rglob("*.md"):
            data_modificacao = datetime.fromtimestamp(arquivo.stat().st_mtime)
            if data_modificacao > limite_tempo:
                with open(arquivo, 'r', encoding='utf-8') as f:
                    conteudo = f.read()
                    # Limita a leitura aos primeiros 1000 caracteres de cada nota para não estourar os tokens
                    arquivos_recentes.append(f"--- Nota: {arquivo.name} ---\n{conteudo[:1000]}...\n")

        if not arquivos_recentes:
            return "Nenhuma anotação foi criada ou modificada nas últimas 24 horas."

        return "\n".join(arquivos_recentes)
    except Exception as e:
        return f"Erro ao ler pasta do Obsidian: {str(e)}"

# ==========================================
# 7. LEITOR DO OBSIDIAN (Histórico de 7 Dias)
# ==========================================
@tool("Obsidian_7d_Reader")
def read_obsidian_7d(pasta_obsidian: str) -> str:
    """
    Lê os arquivos Markdown (.md) do Obsidian criados ou modificados 
    nos últimos 7 dias. Usado para entender a rotina e treinos recentes.
    A entrada deve ser o caminho absoluto da pasta.
    """
    try:
        caminho = Path(pasta_obsidian)
        if not caminho.exists() or not caminho.is_dir():
            return f"Erro: A pasta {pasta_obsidian} não existe."

        limite_tempo = datetime.now() - timedelta(days=7)
        arquivos_recentes = []

        # Busca todos os .md iterando pelas subpastas
        for arquivo in caminho.rglob("*.md"):
            data_modificacao = datetime.fromtimestamp(arquivo.stat().st_mtime)
            
            if data_modificacao > limite_tempo:
                with open(arquivo, 'r', encoding='utf-8') as f:
                    conteudo = f.read()
                    # Limita a 800 caracteres por nota
                    resumo = f"--- Data: {data_modificacao.strftime('%Y-%m-%d')} | Arquivo: {arquivo.name} ---\n{conteudo[:800]}...\n"
                    arquivos_recentes.append((data_modificacao, resumo))

        if not arquivos_recentes:
            return "Nenhuma anotação encontrada nos últimos 7 dias."

        # Ordena os arquivos do mais recente para o mais antigo
        arquivos_recentes.sort(key=lambda x: x[0], reverse=True)
        textos_finais = [item[1] for item in arquivos_recentes]
        
        return "\n".join(textos_finais)
    except Exception as e:
        return f"Erro ao ler pasta do Obsidian (7 dias): {str(e)}"

# ==========================================
# 8. LEITOR DO BANCO DE DADOS DE TREINO (Excel)
# ==========================================
@tool("Training_Database_Access")
def read_local_excel_db() -> str:
    """
    Lê a base de dados de treinos armazenada num ficheiro Excel (.xlsx).
    Se baseia na estrutura do ficheiro Excel e melhora os treinos com base em fatos cientificos.
    """
    file_path = "/home/alexandre.burche@canonical.com/Documents/Pessoal/CrewAI_Journal/Training_db/training.xlsx"
    try:
        caminho = Path(file_path)
        if not caminho.exists():
            return f"Erro: O ficheiro {file_path} não foi encontrado."
        
        # Lê o Excel para um DataFrame do pandas
        df = pd.read_excel(file_path)
        
        # Para não estourar o limite de tokens da IA, pegamos apenas 
        # as últimas 30 linhas (assumindo que as mais recentes ficam no final)
        # Se os seus dados mais recentes ficam no topo, mude de df.tail(30) para df.head(30)
        df_recentes = df.tail(30)
        
        # Converte a tabela para formato Markdown que o LLM entende perfeitamente
        texto_tabela = df_recentes.to_markdown(index=False)
        
        return f"--- ÚLTIMOS REGISTOS DA BASE DE TREINOS ---\n{texto_tabela}\n"
    except Exception as e:
        return f"Erro ao ler a base de dados de treinos em Excel: {str(e)}"

# ==========================================
# 9. CALCULADORA DE CALORIAS E MACROS
# ==========================================
@tool("Calorie_and_Macro_Calculator")
def calculate_macros(peso_kg: float, altura_cm: float, idade: int, genero: str, fator_atividade: float, objetivo: str) -> str:
    """
    Calcula o Gasto Energético Total (TDEE) e a meta de macronutrientes.
    - genero: 'M' (Masculino) ou 'F' (Feminino)
    - fator_atividade: 1.2 (sedentário) até 1.9 (atleta extremo)
    - objetivo: 'perder', 'manter' ou 'ganhar'
    """
    try:
        # Fórmula de Mifflin-St Jeor
        if genero.upper() == 'M':
            bmr = (10 * peso_kg) + (6.25 * altura_cm) - (5 * idade) + 5
        else:
            bmr = (10 * peso_kg) + (6.25 * altura_cm) - (5 * idade) - 161
            
        tdee = bmr * fator_atividade
        
        # Ajuste de objetivo
        if objetivo.lower() == 'perder':
            calorias_alvo = tdee - 500
        elif objetivo.lower() == 'ganhar':
            calorias_alvo = tdee + 300
        else:
            calorias_alvo = tdee
            
        # Divisão padrão esportiva: 30% Proteína, 40% Carboidrato, 30% Gordura
        proteina_g = (calorias_alvo * 0.30) / 4
        carbo_g = (calorias_alvo * 0.40) / 4
        gordura_g = (calorias_alvo * 0.30) / 9
        
        return (
            f"--- METAS NUTRICIONAIS CALCULADAS ---\n"
            f"Calorias Alvo: {int(calorias_alvo)} kcal\n"
            f"Proteínas: {int(proteina_g)}g\n"
            f"Carboidratos: {int(carbo_g)}g\n"
            f"Gorduras: {int(gordura_g)}g\n"
        )
    except Exception as e:
        return f"Erro no cálculo de macros: {str(e)}"

# ==========================================
# 10. LEITOR DE EBOOKS E TRACKER LOCAL
# ==========================================
@tool("Local_Ebook_Reader_and_Tracker")
def read_local_ebook(nome_ficheiro: str) -> str:
    """
    Lê o próximo trecho de 15 minutos (aprox. 4000 caracteres) de um livro local.
    O sistema lembra-se automaticamente de onde parou no dia anterior.
    """
    pasta_livros = Path('/home/alexandre.burche@canonical.com/Documents/Pessoal/CrewAI_Journal/Books/')
    caminho_ficheiro = pasta_livros / nome_ficheiro
    tracker_file = pasta_livros / 'reading_tracker.json'
    
    if not caminho_ficheiro.exists():
        return f"Erro: O ficheiro {nome_ficheiro} não existe na pasta {pasta_livros}."

    tracker = {}
    if tracker_file.exists():
        with open(tracker_file, 'r', encoding='utf-8') as f:
            tracker = json.load(f)
            
    posicao_atual = tracker.get(nome_ficheiro, 0)
    tamanho_trecho = 4000
    texto_completo = ""

    try:
        extensao = caminho_ficheiro.suffix.lower()
        if extensao == '.txt':
            with open(caminho_ficheiro, 'r', encoding='utf-8') as f:
                texto_completo = f.read()
        elif extensao == '.pdf':
            with open(caminho_ficheiro, 'rb') as f:
                leitor = PyPDF2.PdfReader(f)
                for pagina in leitor.pages:
                    texto_extraido = pagina.extract_text()
                    if texto_extraido:
                        texto_completo += texto_extraido + "\n"
        elif extensao == '.epub':
            livro = epub.read_epub(str(caminho_ficheiro))
            for item in livro.get_items():
                if item.get_type() == ebooklib.ITEM_DOCUMENT:
                    soup = BeautifulSoup(item.get_body_content(), 'html.parser')
                    texto_completo += soup.get_text(separator='\n') + "\n"
        else:
            return f"Erro: Formato {extensao} não suportado."

        if posicao_atual >= len(texto_completo):
            return f"O livro {nome_ficheiro} já foi lido até ao fim!"
            
        fim_estimado = posicao_atual + tamanho_trecho
        
        # PROCURA O FIM DA FRASE: Procura por '.', '?' ou '!' em vez de '\n'
        match = re.search(r'[.!?]["\']?(?=\s|\n|$)', texto_completo[fim_estimado:])
        
        if match:
            fim_real = fim_estimado + match.end()
        else:
            fim_real = len(texto_completo)
            
        trecho_hoje = texto_completo[posicao_atual : fim_real].strip()
        
        # LIMPEZA MÁGICA DO PDF: Remove quebras de linha no meio de frases 
        # (substitui um único \n por espaço, mas mantém parágrafos reais \n\n)
        trecho_hoje = re.sub(r'(?<!\n)\n(?!\n)', ' ', trecho_hoje)
        
        tracker[nome_ficheiro] = fim_real
        with open(tracker_file, 'w', encoding='utf-8') as f:
            json.dump(tracker, f)
            
        return (
            f"--- TRECHO DE LEITURA: {nome_ficheiro} ---\n"
            f"Progresso: {posicao_atual}/{len(texto_completo)} caracteres.\n\n"
            f"{trecho_hoje}\n"
        )
    except Exception as e:
        return f"Erro ao processar o livro {nome_ficheiro}: {str(e)}"

# ==========================================
# 11. GOOGLE WORKSPACE (Auth, Gmail, Calendar, Drive)
# ==========================================
# Permissões (Scopes) estritas apenas para leitura
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/drive.readonly'
]

def get_google_credentials():
    """Lida com a autenticação. Na primeira vez, abre o navegador para login."""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds

@tool("Gmail_Reader")
def read_recent_emails(max_results: int = 5) -> str:
    """Lê os últimos e-mails não lidos da caixa de entrada do Gmail."""
    try:
        creds = get_google_credentials()
        service = build('gmail', 'v1', credentials=creds)
        results = service.users().messages().list(userId='me', labelIds=['INBOX', 'UNREAD'], maxResults=max_results).execute()
        messages = results.get('messages', [])
        
        if not messages:
            return "Nenhum e-mail não lido."
        
        email_texts = []
        for msg in messages:
            msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
            headers = msg_data['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'Sem Assunto')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Desconhecido')
            email_texts.append(f"- De: {sender} | Assunto: {subject}")
        return "\n".join(email_texts)
    except Exception as e:
        return f"Erro no Gmail: {str(e)}"

@tool("Calendar_API")
def read_todays_calendar() -> str:
    """Busca os eventos do Google Calendar agendados para hoje."""
    try:
        creds = get_google_credentials()
        service = build('calendar', 'v3', credentials=creds)
        
        # Define o intervalo de tempo para hoje (UTC)
        agora = datetime.now(timezone.utc)
        inicio_dia = agora.replace(hour=0, minute=0, second=0).isoformat() + 'Z'
        fim_dia = (agora + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0).isoformat() + 'Z'
        
        events_result = service.events().list(calendarId='primary', timeMin=inicio_dia, timeMax=fim_dia,
                                              maxResults=10, singleEvents=True, orderBy='startTime').execute()
        events = events_result.get('items', [])
        
        if not events:
            return "Nenhum evento agendado para hoje."
        
        agenda = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            agenda.append(f"- {start}: {event['summary']}")
        return "--- AGENDA DE HOJE ---\n" + "\n".join(agenda)
    except Exception as e:
        return f"Erro no Calendar: {str(e)}"

@tool("Drive_Access")
def search_drive() -> str:
    """Busca os 5 ficheiros modificados mais recentemente no Google Drive."""
    try:
        creds = get_google_credentials()
        service = build('drive', 'v3', credentials=creds)
        
        results = service.files().list(pageSize=5,
                                       fields="nextPageToken, files(id, name, modifiedTime)",
                                       orderBy="modifiedTime desc").execute()
        items = results.get('files', [])
        
        if not items:
            return "Nenhum ficheiro recente encontrado no Drive."
        
        files_str = []
        for item in items:
            files_str.append(f"- {item['name']} (Modificado em: {item['modifiedTime']})")
        return "--- ARQUIVOS RECENTES DO DRIVE ---\n" + "\n".join(files_str)
    except Exception as e:
        return f"Erro no Drive: {str(e)}"

# ==========================================
# 12. LEITOR DE EBOOKS DA INTERNET E TRACKER
# ==========================================
@tool("Internet_Free_Book_Reader_and_Tracker")
def read_internet_ebook(url: str) -> str:
    """
    Lê o próximo trecho de 15 minutos (aprox. 4000 caracteres) de um livro online gratuito.
    A entrada deve ser um URL direto para o ficheiro de texto (.txt) do livro (ex: Project Gutenberg).
    O sistema lembra-se automaticamente de onde parou.
    """
    try:
        # Cria um ID único para o URL para usar como chave no ficheiro JSON
        url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()
        
        # Usa a mesma pasta de livros para guardar o tracker online
        pasta_livros = Path('/home/alexandre.burche@canonical.com/Documents/Pessoal/CrewAI_Journal/Books')
        pasta_livros.mkdir(parents=True, exist_ok=True)
        tracker_file = pasta_livros / 'online_reading_tracker.json'
        
        tracker = {}
        if tracker_file.exists():
            with open(tracker_file, 'r', encoding='utf-8') as f:
                tracker = json.load(f)
                
        posicao_atual = tracker.get(url_hash, 0)
        tamanho_trecho = 4000
        
        # Descarrega o texto da internet
        response = requests.get(url)
        response.raise_for_status()
        texto_completo = response.text
        
        # =========================================================
        # ALTERAÇÃO AQUI: Lógica de corte até o final do parágrafo
        # =========================================================
        if posicao_atual >= len(texto_completo):
            return "O livro online já foi lido até ao fim!"
            
        fim_estimado = posicao_atual + tamanho_trecho
        fim_real = texto_completo.find('\n', fim_estimado)
        
        # Se não encontrar nenhuma quebra de linha até o fim do texto
        if fim_real == -1:
            fim_real = len(texto_completo)
            
        trecho_hoje = texto_completo[posicao_atual : fim_real].strip()
        
        # Atualiza e guarda a posição exata no marcador
        tracker[url_hash] = fim_real
        with open(tracker_file, 'w', encoding='utf-8') as f:
            json.dump(tracker, f)
            
        return (
            f"--- TRECHO DE LEITURA ONLINE ---\n"
            f"URL: {url}\n"
            f"Progresso: {posicao_atual}/{len(texto_completo)} caracteres.\n\n"
            f"{trecho_hoje}\n"
        )
    except Exception as e:
        return f"Erro ao ler o livro online: {str(e)}"

# ==========================================
# 13. BANCO DE DADOS DE TREINOS ONLINE (ExerciseDB)
# ==========================================
@tool("ExerciseDB_API")
def fetch_online_exercises(equipment: str) -> str:
    """
    Busca exercícios de musculação no banco de dados online ExerciseDB.
    A entrada deve ser o tipo de equipamento em inglês (ex: 'dumbbell', 'body weight', 'barbell', 'cable').
    """
    api_key = os.getenv("RAPIDAPI_KEY")
    if not api_key:
        return "Erro: RAPIDAPI_KEY não configurada no .env"

    url = f"https://exercisedb.p.rapidapi.com/exercises/equipment/{equipment}"
    
    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": "exercisedb.p.rapidapi.com"
    }
    
    # Parâmetro 'limit' restringe os resultados para não exceder o limite de tokens da IA
    querystring = {"limit": "10"} 

    try:
        response = requests.get(url, headers=headers, params=querystring)
        response.raise_for_status()
        data = response.json()
        
        if not data:
            return f"Nenhum exercício encontrado para o equipamento: {equipment}."
        
        resultados = []
        for ex in data:
            nome = ex.get("name", "").title()
            alvo = ex.get("target", "").title()
            parte = ex.get("bodyPart", "").title()
            # A API também retorna GIFs ilustrativos, mas para texto focamos nos nomes e músculos
            resultados.append(f"- {nome} (Foco: {alvo} | Região: {parte})")
            
        return f"--- SUGESTÕES DE EXERCÍCIOS ONLINE ({equipment.upper()}) ---\n" + "\n".join(resultados)
    except Exception as e:
        return f"Erro ao aceder à ExerciseDB: {str(e)}"

# ==========================================
# 14. BANCO DE DADOS DE INGREDIENTES E RECEITAS (Open Food Facts API)
# ==========================================
@tool("Recipes_Database_Access")
def search_open_food_facts(termo_busca: str) -> str:
    """
    Busca informações nutricionais de ingredientes e alimentos no Open Food Facts.
    A entrada deve ser o nome do ingrediente ou alimento (ex: 'oats', 'greek yogurt', 'chicken breast').
    """
    try:
        url = "https://world.openfoodfacts.org/cgi/search.pl"
        params = {
            "search_terms": termo_busca,
            "search_simple": 1,
            "action": "process",
            "json": 1,
            "page_size": 3
        }
        
        # A API exige um User-Agent identificado nas boas práticas
        headers = {
            "User-Agent": "BurcheTimesJournalApp - Linux - Version 2.0"
        }
        
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        products = data.get("products", [])
        if not products:
            return f"Nenhum produto ou ingrediente encontrado para: '{termo_busca}'."
            
        resultados = []
        for prod in products:
            nome = prod.get("product_name", "Desconhecido")
            nutriments = prod.get("nutriments", {})
            
            calorias = nutriments.get("energy-kcal_100g", "N/A")
            proteinas = nutriments.get("proteins_100g", "N/A")
            carbos = nutriments.get("carbohydrates_100g", "N/A")
            gorduras = nutriments.get("fat_100g", "N/A")
            
            resultados.append(
                f"- **{nome}** (por 100g):\n"
                f"  Calorias: {calorias} kcal | Proteínas: {proteinas}g | Carboidratos: {carbos}g | Gorduras: {gorduras}g"
            )
            
        return f"--- INFORMAÇÕES NUTRICIONAIS (OPEN FOOD FACTS) PARA '{termo_busca.upper()}' ---\n" + "\n\n".join(resultados)
    except Exception as e:
        return f"Erro ao acessar Open Food Facts: {str(e)}"
