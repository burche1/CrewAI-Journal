import os
import json
import textwrap
import ast
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process
from pydantic import BaseModel, Field
from pathlib import Path
from typing import List
from crewai import LLM
from datetime import datetime
import markdown
from weasyprint import HTML, CSS
from tools import read_local_file, fetch_chess_puzzle, generate_sudoku, fetch_weather, read_obsidian_7d, search_internet, read_recent_obsidian_notes, read_local_excel_db, calculate_macros, read_local_ebook, read_recent_emails, read_todays_calendar, search_drive, read_internet_ebook, fetch_online_exercises, search_open_food_facts

# Load environment variables (.env)
load_dotenv()

# Isso vai gerar algo como "2026-10-10" e "Saturday"
data_atual = datetime.now().strftime("%Y-%m-%d")
dia_da_semana = datetime.now().strftime("%A")

# ==========================================
# 00. CONFIGURAÇÃO DOS LLMs (Controle de Custo)
# ==========================================
# Modelo rápido e barato para os agentes de coleta e rascunho
llm_mini = LLM(
    model="gpt-4o-mini",
    temperature=0.4 # Temperatura um pouco maior para criatividade em receitas e treinos
)

# Modelo avançado (mais caro) exclusivo para revisão crítica e formatação
llm_pro = LLM(
    model="gpt-4o",
    temperature=0.1 # Temperatura baixa para ser extremamente lógico e rígido na formatação
)

# ==========================================
# 0. DATA STRUCTURES
# ==========================================

# 1. Training Branch Output
class TrainingPlan(BaseModel):
    warmup: str = Field(description="Warmup routine")
    main_workout: str = Field(description="Main exercises, sets, and reps (dumbbells/bench/cardio)")
    cooldown: str = Field(description="Stretching or yoga cooldown")
    academic_tips: List[str] = Field(description="Scientific tips for injury prevention")

# 2. Nutrition Branch Output
class DailyDiet(BaseModel):
    target_calories: int
    protein_g: int
    carbs_g: int
    fats_g: int
    meal_options: List[str] = Field(description="3 distinct meal plan options with recipes")

# 3. News Branch Output
class NewsItem(BaseModel):
    topic: str = Field(description="What is new on technology, Games, news on Linux and Ubuntu, top news for Brazil, or top news for Germany")
    headline: str
    fact_checked_summary: str
    image_markdown: str = Field(description="Markdown image syntax like ![alt text](url) if an image was provided, otherwise empty")

class DailyNews(BaseModel):
    weather_greeting: str = Field(description="The exact text summary provided after WEATHER_GREETING.")
    weather_tables: str = Field(description="The exact Markdown tables provided after WEATHER_TABLES. DO NOT REMOVE ANY ROWS OR EMOJIS.")
    top_news: List[NewsItem]

# 4. Personal Assistant Branch Output
class DailyBriefing(BaseModel):
    philosophical_quote: str
    yesterday_summary: str
    today_schedule: List[str]
    meeting_prep_notes: str

# 5. Main Editor Final Output
class FinalNewspaper(BaseModel):
    weather_summary_table: str = Field(description="The EXACT markdown table for daily summary. DO NOT change or remove it.")
    weather_hourly_table: str = Field(description="The EXACT markdown table for the 24-hour forecast. DO NOT drop any rows or emojis.")
    daily_briefing: str = Field(description="Summary of yesterday, today's schedule, and philosophical quote.")
    top_news: List[NewsItem] = Field(description="Top news articles with headlines, summaries, and image links.")
    workout_plan: str = Field(description="Workout plan with warm-up, main workout, cardio, and cool-down.")
    nutrition: str = Field(description="3 complete meal options with recipes and macros.")
    chess_puzzle: str = Field(description="Chess puzzle image link provided by the auditor.")
    sudoku_game: str = Field(description="Sudoku HTML table provided by the auditor.")
    reading_excerpt: str = Field(description="Full, unedited text excerpt from the book.")
    chess_solution: str = Field(description="Solution steps for the chess puzzle.")

# 6. Intellectual Branch Output
class ChessPuzzle(BaseModel):
    fen_or_board: str = Field(
        description="MUST be the exact Markdown image link provided by the tool."
    )
    solution: str = Field(
        description="List of UCI moves. Output as a string representation of the list."
    )

class SudokuGame(BaseModel):
    grid: str = Field(description="MUST be the exact HTML table starting with <table class='sudoku-board'>. DO NOT strip or change the HTML tags.")
    difficulty: str

class BookReading(BaseModel):
    book_title: str
    start_page: int
    reading_excerpt: str = Field(description="The EXACT and FULL text provided by the reading tool. DO NOT summarize, paraphrase, or truncate it. You must output every single word of the excerpt.")

class DailyIntellect(BaseModel):
    chess: ChessPuzzle
    sudoku: SudokuGame
    reading: BookReading

# ==========================================
# 1. TOOLS
# ==========================================

tools_local_txt = [read_local_file]                 # access to local text files
tools_chess = [fetch_chess_puzzle]                  # access to daily chess puzzles
tools_sudoku = [generate_sudoku]                    # access to sudoku puzzles
tools_weather = [fetch_weather]                     # access to weather information
tools_internet = [search_internet]                  # access to the internet for web searches
tools_news = [search_internet]                      # Podemos reutilizar o Serper para notícias e para checagem
tools_fact_checking = [search_internet]             # access to the internet for fact-checking information
tools_obsidian_all = [read_recent_obsidian_notes]   # access to all recent Obsidian notes
tools_obsidian_7d = [read_obsidian_7d]              # access to Obsidian notes from the last 7 days
tools_training_db_local = [read_local_excel_db]     # access to the local training database in Excel format
tools_calculator = [calculate_macros]               # calculator and mathematical tools for calculating calories and macros
tools_reading = [read_local_ebook]                                              # access to local ebook reader and tracker
tools_workspace = [read_recent_emails, read_todays_calendar, search_drive]      # access to workspace tools like email, calendar, and drive
tools_reading_internet = [read_internet_ebook]                                  # access to internet-free ebook reader and tracker
tools_training_db_online = [] # access to the training database which will be a online database - fetch_online_exercises
tools_recipes_db = [search_open_food_facts]         # access to recipes database

# ==========================================
# 2. DEFINITION OF AGENTS
# ==========================================

# --- BRANCH 1: TRAINING ---
personal_trainer = Agent(
    role="Elite Personal Trainer",
    goal="Analyze past diary entries to plan today's workout balancing endurance, strength, and recovery.",
    backstory="You are a high-level triathlon and fitness coach. You adapt workouts to available equipment (home gym with dumbbells and bench only). You are an expert in periodization, scheduling rest, stretching, yoga, bike, run, and swim sessions. The path to the Obsidian vault is '/home/alexandre.burche@canonical.com/Documents/Obsidian/MyVault'.",
    verbose=True,
    llm=llm_mini,
    tools=tools_obsidian_all + tools_internet + tools_training_db_local + tools_training_db_online
)

training_expert = Agent(
    role="High-Performance Academic Sports Scientist",
    goal="Review, correct, and refine the Personal Trainer's plan, adding evidence-based academic insights.",
    backstory="You have a PhD in Sports Science. You never accept a raw workout plan without analyzing its biomechanical and physiological impact. You provide valuable, highly technical tips for injury prevention and maximum performance.",
    verbose=True,
    llm=llm_mini,  # <--- Modelo barato
)

# --- BRANCH 2: NUTRITION ---
nutritionist = Agent(
    role="Clinical Sports Nutritionist",
    goal="Provide 3 precise daily diet options with recipes based on the user's training load and macro needs.",
    backstory="You are an expert in sports nutrition. My profile: 33 years old, male, 80kg, 191cm, activity factor 1.25, goal: get stronger and faster. You read the user's diary to understand their energy expenditure. You always provide 3 varied meal plans (options) that hit exact macronutrient and caloric targets, including easy-to-follow recipes. The path to the Obsidian vault is '/home/alexandre.burche@canonical.com/Documents/Obsidian/MyVault', and inside 00_Journals you can find all my diaries.",
    verbose=True,
    llm=llm_mini,
    tools=tools_obsidian_7d + tools_calculator + tools_recipes_db
)

# --- BRANCH 3: NEWS & WORLD ---
journalist = Agent(
    role="Senior Tech and World Journalist",
    goal="Gather precise weather data and breaking news on specific topics: Games, Tech, Linux, Brazil, and Germany.",
    backstory="You are a fast-paced journalist with a keen eye for relevant news. You avoid fluff and go straight to the facts regarding technology, Linux ecosystems, gaming, and geopolitical updates from Brazil and Germany.",
    verbose=True,
    llm=llm_mini,
    tools=tools_internet + tools_weather
)

expert_journalist = Agent(
    role="Senior Fact-Checker and Managing Editor",
    goal="Fact-check the Journalist's news, expand on critical details, and ensure absolute accuracy.",
    backstory="You are a rigorous fact-checker. You verify every claim made by reporters. If a piece of news is superficial, you dig deeper and enrich it with valuable context. You do not tolerate fake news or clickbait.",
    verbose=True,
    llm=llm_mini, # Lembra que mudamos para mini para testar os custos
    tools=tools_internet # Usa a internet para checar os fatos
)

# --- BRANCH 4: PERSONAL ASSISTANT & WORK ---
personal_assistant = Agent(
    role="Executive Personal Assistant",
    goal="Summarize the previous day, outline today's schedule, and set the tone with a philosophical quote.",
    backstory="You are an incredibly organized executive assistant. You have full access to the user's life (calendar, emails, drive). You are stoic, focused on extreme productivity, and provide clarity for the day ahead. The path to the Obsidian vault is '/home/alexandre.burche@canonical.com/Documents/Obsidian/MyVault', and inside 00_Journals is my diary.",
    verbose=True,
    llm=llm_mini,
    tools=tools_obsidian_all + tools_workspace
)

deep_researcher = Agent(
    role="Chief of Staff & Deep Researcher",
    goal="Deep dive into notes, transcripts, and meetings to create a comprehensive, detailed summary and provide meeting prep.",
    backstory="You act as the ultimate Chief of Staff. You loop through meeting notes and transcripts to connect the dots. You provide actionable advice on how the user should prepare for today's meetings based on historical context. The path to the Obsidian vault is '/home/alexandre.burche@canonical.com/Documents/Obsidian/MyVault', and inside 00_Journals is my diary.",
    verbose=True, 
    llm=llm_mini,
    tools=tools_obsidian_all + tools_workspace
)

# --- BRANCH 5: INTELLECTUAL ---
intellectual_agent = Agent(
    role="Intellectual Curator & Game Master",
    goal="Provide a daily chess puzzle, a day-scaled Sudoku, and a 15-minute book reading segment.",
    backstory="You are a brilliant polymath. You believe the brain must be trained daily. You fetch chess puzzles, generate Sudoku grids that get harder throughout the week (Sunday is the hardest), and curate continuous book readings, always remembering where the user stopped yesterday.",
    verbose=True,
    llm=llm_mini,
    tools=tools_chess + tools_sudoku + tools_reading + tools_reading_internet
)

auditor_agent = Agent(
    role="Puzzle Auditor & Quality Controller",
    goal="Verify the solvability of the chess and Sudoku puzzles, returning them for correction if invalid.",
    backstory="You are a strict logician and grandmaster. You hate broken puzzles. You meticulously audit the Intellectual Agent's games. If a Sudoku has no solution or the chess FEN does not match the solution, you aggressively fix it or demand a valid one before passing the data forward.",
    verbose=True,
    llm=llm_mini
)

# --- FINAL STAGE: MAIN EDITOR ---
main_editor = Agent(
    role="Master Newspaper Designer & Editor-in-Chief",
    goal="Compile all branched information into a visually appealing, perfectly structured markdown newspaper template.",
    backstory="You are an award-winning layout designer and editor. You know exactly where each section belongs. You format the final output using beautiful Markdown structures (headers, bolding, blockquotes) so it feels like reading a premium printed newspaper.",
    verbose=True,
    llm=llm_mini,  # <--- Modelo barato
)

# ==========================================
# 3. DEFINITION OF TASKS
# ==========================================

# Branch 1 Tasks
task_train_draft = Task(
    description="Read the diary, check the training database, and draft today's workout plan (using only dumbbells/bench or cardio/yoga).",
    expected_output="A structured workout draft for today.",
    agent=personal_trainer
)

task_train_refine = Task(
    description="Review the personal trainer's draft. Correct errors and add academic/high-performance tips.",
    expected_output="A refined, scientifically backed training plan.",
    agent=training_expert,
    context=[task_train_draft], # Waits for the trainer to finish
    output_pydantic=TrainingPlan # <--- Forces the agent to output this exact structure
)

# Branch 2 Task
task_nutrition = Task(
    description="Read the diary to understand the training load. Propose 3 complete diet options with recipes and exact macros.",
    expected_output="3 diet options covering exact macros and calories, including recipes.",
    agent=nutritionist,
    context=[task_train_draft], # Needs to know the workout to calculate calories
    output_pydantic=DailyDiet # <--- Forces the agent to output this exact structure
)

# Branch 3 Tasks
task_news_draft = Task(
    description=(
        "Today is {current_day}, {current_date}. "
        "Search for major daily breaking news in Tech, Gaming, Linux, Germany, and Brazil. "
        "CRITICAL INSTRUCTION: Perform ONLY ONE OR TWO consolidated search queries (e.g., 'top technology gaming linux news Germany Brazil today') "
        "to avoid rate limits on search tools."
    ),
    expected_output="A consolidated list of breaking news items.",
    agent=journalist
)

task_news_refine = Task(
    description="Fact-check the news draft. Expand on important topics and remove any inaccuracies.",
    expected_output="A highly accurate, enriched news section.",
    agent=expert_journalist,
    context=[task_news_draft], # Waits for the journalist to finish
    output_pydantic=DailyNews # <--- Forces the agent to output this exact structure
)

# Branch 4 Tasks
task_pa_draft = Task(
    description="Today is {current_day}, {current_date}. Summarize yesterday's events, list today's agenda, and provide a philosophical quote.",
    expected_output="A daily briefing with schedule and quote.",
    agent=personal_assistant
)

task_researcher_deep_dive = Task(
    description="Analyze the PA's briefing, dive deep into meeting transcripts/notes, and provide a detailed preparation guide for today's meetings.",
    expected_output="A comprehensive prep guide and deep-dive summary of current projects.",
    agent=deep_researcher,
    context=[task_pa_draft], # Waits for the PA to finish
    output_pydantic=DailyBriefing # <--- Forces the agent to output this exact structure
)

# Branch 5 Tasks
task_intellect_draft = Task(
    description=(
        "Today is {current_day}. Fetch a chess puzzle and its solution. "
        "Generate a Sudoku game with a difficulty appropriate for {current_day} (Sunday is the hardest). "
        "Finally, fetch the next 15-minute reading chunk. "
        "CRITICAL RULES: "
        "1. For the Sudoku, the tool returns an HTML table. You MUST pass this exact HTML table forward. Do not convert it to plain text. "
        "2. For the Chess puzzle, pass the exact Markdown image string forward. "
        "3. The user configured the reading source as '{reading_source}'. If the source is 'local', use the Local Ebook Reader tool with the file '{local_book}'. If the source is 'internet', use the Internet Ebook Reader tool with the URL '{internet_url}'."
    ),
    expected_output="A raw compilation of the chess puzzle (with markdown image), Sudoku game (with HTML table), and reading segment.",
    agent=intellectual_agent
)

task_intellect_audit = Task(
    description=(
        "Review the puzzles from the Intellectual Agent. Ensure the Sudoku is solvable. Verify the chess solution matches the board. "
        "CRITICAL FORMATTING RULES: "
        "1. For Chess, your 'fen_or_board' field MUST contain the exact Markdown image link (e.g., ![Chess Board](url)). Do not just write the FEN string. "
        "2. For Sudoku, your 'grid' field MUST contain the exact HTML table with the class 'sudoku-board'. DO NOT convert it to text."
    ),
    expected_output="A validated set of puzzles, keeping the exact HTML and Markdown image formatting intact.",
    agent=auditor_agent,
    context=[task_intellect_draft], 
    output_pydantic=DailyIntellect 
)

# Final Task (Editor)
task_final_edit = Task(
    description=(
        "Take all the refined data from the Training Expert, Nutritionist, Expert Journalist, Deep Researcher, and Puzzle Auditor. "
        "Format everything into the final newspaper layout.\n"
        "CRITICAL RULE - STRICT SECTION ORDERING:\n"
        "1. Weather: Place the daily summary table inside 'weather_summary_table'. Place the 24h table inside 'weather_hourly_table'. DO NOT change the formatting.\n"
        "2. Daily Briefing & Schedule\n"
        "3. Top News (with image links `![alt text](url)`)\n"
        "4. Workout Plan\n"
        "5. Nutrition (3 meals)\n"
        "6. Chess Puzzle (Board Image ONLY Markdown link)\n"
        "7. Sudoku (HTML table ONLY)\n"
        "8. Reading Excerpt (Full text, DO NOT cut)\n"
        "9. Chess Puzzle Solution\n\n"
        "DO NOT write section title headers inside the individual field values. Output ONLY the raw content for each field."
    ),
    expected_output="The complete, perfectly ordered Pydantic FinalNewspaper.",
    agent=main_editor,
    context=[task_train_refine, task_nutrition, task_news_refine, task_researcher_deep_dive, task_intellect_audit], 
    output_pydantic=FinalNewspaper 
)

# ==========================================
# 4. CREW ORCHESTRATION - UPDATED
# ==========================================
journal_crew = Crew(
    agents=[
        personal_trainer, training_expert, 
        nutritionist, 
        journalist, expert_journalist, 
        personal_assistant, deep_researcher,
        intellectual_agent, auditor_agent, # <--- New Agents
        main_editor
    ],
    tasks=[
        task_train_draft, task_train_refine, 
        task_nutrition, 
        task_news_draft, task_news_refine, 
        task_pa_draft, task_researcher_deep_dive,
        task_intellect_draft, task_intellect_audit, # <--- New Tasks
        task_final_edit
    ],
    process=Process.sequential, 
    verbose=True,
    output_log_file="historico_agentes.log"
)

def format_chess_solution(solution_raw: str) -> str:
    """Converte uma lista de lances UCI em formato impresso organizado:

    1. e2    e5
    2. c5    f2
    """
    if not solution_raw:
        return ""

    # Converte string no formato "['e2e5', 'c5f2']" para lista Python real
    try:
        moves = ast.literal_eval(solution_raw)
    except Exception:
        # Fallback caso já venha limpo ou em formato texto
        clean_str = (
            str(solution_raw)
            .replace("[", "")
            .replace("]", "")
            .replace("'", "")
            .replace('"', "")
        )
        moves = [m.strip() for m in clean_str.split(",") if m.strip()]

    formatted_lines = []
    for idx, move in enumerate(moves, start=1):
        m = str(move).strip()
        # Se for um lance UCI padrão de 4 caracteres (ex: 'e2e5')
        if len(m) == 4:
            origem = m[:2]
            destino = m[2:]
            # Usamos &nbsp;&nbsp;&nbsp;&nbsp; para dar um espaçamento limpo entre origem e destino
            formatted_lines.append(
                f"{idx}. {origem} &nbsp;&nbsp;&nbsp;&nbsp; {destino}"
            )
        else:
            formatted_lines.append(f"{idx}. {m}")

    # Retorna cada lance numa nova linha com quebra de linha do Markdown ('  \n')
    return "  \n".join(formatted_lines)

if __name__ == "__main__":
    print("Starting Burche Times newsroom operations...")
    
    # Lê o ficheiro de configuração
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # 1. Definimos o dicionário de variáveis (agora com as configurações de leitura)
    variaveis_dinamicas = {
        'current_date': data_atual,
        'current_day': dia_da_semana,
        'location': 'Offenbach, Hessen, Germany',
        'reading_source': config['leitura']['fonte'],
        'local_book': config['leitura']['livro_local_nome'],
        'internet_url': config['leitura']['livro_internet_url']
    }
    
    # 2. Injetamos as variáveis no kickoff
    final_edition = journal_crew.kickoff(inputs=variaveis_dinamicas)
    
    # Executa a busca do clima diretamente no Python para atualizar os arquivos em /tmp
    clima_bruto = fetch_weather.func("Offenbach, Hessen, Germany")

    greeting_file = Path('/tmp/weather_greeting.txt')
    tables_file = Path('/tmp/weather_tables.txt')

    frase_clima = greeting_file.read_text(encoding='utf-8').strip() if greeting_file.exists() else "here is your daily briefing."
    weather_tables = tables_file.read_text(encoding='utf-8').strip() if tables_file.exists() else clima_bruto

    if final_edition.pydantic:
        p = final_edition.pydantic

        # Formata notícias
        noticias_md = ""
        for item in p.top_news:
            noticias_md += f"### {item.headline}\n"
            if item.image_markdown and item.image_markdown.strip():
                noticias_md += f"{item.image_markdown}\n\n"
            noticias_md += f"{item.fact_checked_summary}\n\n"

        # Lê os arquivos do clima salvos em /tmp pelo fetch_weather
        tables_file = Path('/tmp/weather_tables.txt')
        weather_tables = tables_file.read_text(encoding='utf-8').strip() if tables_file.exists() else ""

        # Converte o CONTEÚDO das seções (sem incluir o h2 no markdown para melhor controle)
        weather_content_html = markdown.markdown(weather_tables, extensions=["tables"])
        briefing_content_html = markdown.markdown(p.daily_briefing, extensions=["tables"])
        news_content_html = markdown.markdown(noticias_md, extensions=["tables"]) if noticias_md.strip() else ""
        workout_content_html = markdown.markdown(p.workout_plan, extensions=["tables"])
        nutrition_content_html = markdown.markdown(p.nutrition, extensions=["tables"])
        chess_content_html = markdown.markdown(p.chess_puzzle, extensions=["tables"])
        excerpt_content_html = markdown.markdown(p.reading_excerpt, extensions=["tables"])
        solution_content_html = markdown.markdown(format_chess_solution(p.chess_solution), extensions=["tables"])

        sudoku_html = getattr(p, 'sudoku_game', '')
        if not sudoku_html or '<table' not in sudoku_html:
            sudoku_html = generate_sudoku(dia_da_semana)

    else:
        html_body = markdown.markdown(final_edition.raw, extensions=["tables"])
        sudoku_html = generate_sudoku(dia_da_semana)

    # Monta a estrutura HTML perfeita:
    # - Títulos (h2) ficam em largura total
    # - Texto corrido (Briefing, News, Workout, Nutrition, Excerpt) fica dentro de <div class="two-columns">
    # - Elementos especiais (Clima, Xadrez, Sudoku, Solução) ficam dentro de <div class="full-width">
    
    news_block = f"<h2>Top News</h2><div class='two-columns'>{news_content_html}</div>" if news_content_html else ""

    html_body = f"""
    <h2>Weather Forecast</h2>
    <div class="full-width">
        {weather_content_html}
    </div>

    <h2>Daily Briefing & Schedule</h2>
    <div class="two-columns">
        {briefing_content_html}
    </div>

    {news_block}

    <h2>Workout Plan</h2>
    <div class="two-columns">
        {workout_content_html}
    </div>

    <h2>Nutrition</h2>
    <div class="two-columns">
        {nutrition_content_html}
    </div>

    <h2>Chess Puzzle</h2>
    <div class="full-width">
        {chess_content_html}
    </div>

    <h2>Sudoku</h2>
    <div class="full-width" style="text-align: center;">
        {sudoku_html}
    </div>

    <h2>Reading Excerpt</h2>
    <div class="two-columns">
        {excerpt_content_html}
    </div>

    <h2>Chess Puzzle Solution</h2>
    <div class="full-width chess-solution">
        {solution_content_html}
    </div>
    """

    # Lê a frase de saudação
    greeting_file = Path('/tmp/weather_greeting.txt')
    frase_clima = greeting_file.read_text(encoding='utf-8').strip() if greeting_file.exists() else "here is your daily briefing."

    # Data por extenso
    dia_num = datetime.now().day
    sufixo = "th" if 11 <= dia_num <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(dia_num % 10, "th")
    data_extenso = datetime.now().strftime(f"{dia_num}{sufixo} of %B, %Y")
    
    saudacao = (
        f"<p class='hero-greeting'>Hi Alexandre, good morning! "
        f"Today is {data_extenso}. It is a {dia_da_semana} and {frase_clima} "
        f"Here is your daily journal.</p>"
    )

    # Documento HTML completo (sem a classe .content em volta de tudo para não quebrar o layout)
    html_completo = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Burche Times</title>
    </head>
    <body>
        <h1>The Burche Times</h1>
        {saudacao}
        <main>
            {html_body}
        </main>
    </body>
    </html>
    """

    pasta_destino = "/home/alexandre.burche@canonical.com/Documents/Pessoal/CrewAI_Journal/Editions"
    os.makedirs(pasta_destino, exist_ok=True)
    nome_pdf = f"{pasta_destino}/Burche_Times_{data_atual}.pdf"
    
    print("\nGerando o PDF do jornal...")
    HTML(string=html_completo).write_pdf(nome_pdf, stylesheets=[CSS('layout.css')])
    print(f"✅ Concluído! Jornal salvo em: {nome_pdf}")
