import os
import json
import textwrap
import ast
import re
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process
from pydantic import BaseModel, Field
from pathlib import Path
from typing import List
from crewai import LLM
from datetime import datetime
import markdown
from weasyprint import HTML, CSS
from tools import read_local_file, fetch_chess_puzzle, generate_sudoku, fetch_weather, read_obsidian_7d, search_internet, read_recent_obsidian_notes, calculate_macros, read_local_ebook, read_recent_emails, read_todays_calendar, search_drive, read_internet_ebook, fetch_online_exercises, search_open_food_facts, fetch_obsidian_training_session
from settings import (
    PROJECT_ROOT, JOURNAL_CONFIG_FILE, JOURNAL_OUTPUT_DIR,
    JOURNAL_STYLE_FILE, JOURNAL_NOTES_PATH, runtime_file,
)

# Load environment variables (.env)
load_dotenv(PROJECT_ROOT / ".env")

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
    workout_plan: str = Field(description="The exact daily workout plan extracted directly from the Obsidian training file.")

# 2. Nutrition Branch Output
class DailyDiet(BaseModel):
    target_calories_total: int = Field(
        description="Total daily target calories."
    )
    basal_calories: int = Field(description="Basal Metabolic Rate (BMR).")
    exercise_calories: int = Field(
        description="Calories burned from exercise and training load."
    )
    protein_g: int = Field(description="Target protein in grams.")
    carbs_g: int = Field(description="Target carbohydrates in grams.")
    fats_g: int = Field(description="Target fats in grams.")
    meal_options: List[str] = Field(
        description="Exactly 3 structured meal plans: 'Meal 1 - Breakfast', 'Meal 2 - Lunch', and 'Meal 3 - Dinner', with full ingredients, recipes, and exact macros."
    )

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
    nutrition_targets_table: str = Field(description="A clean Markdown table summarizing: Total Target Calories, Basal Calories (BMR), Exercise Calories, Protein, Carbs, and Fats.")
    nutrition_meals: str = Field(description="The 3 meal options formatted as '### Meal 1 - Breakfast', '### Meal 2 - Lunch', and '### Meal 3 - Dinner'.")
    chess_puzzle: str = Field(description="Chess puzzle instruction prompt (who plays & objective) and the board image link provided by the auditor.")
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
tools_training = [fetch_obsidian_training_session, read_obsidian_7d]            # access to the local training plan in the Obsidian vault
tools_calculator = [calculate_macros]                                           # calculator and mathematical tools for calculating calories and macros
tools_reading = [read_local_ebook]                                              # access to local ebook reader and tracker
tools_workspace = [read_recent_emails, read_todays_calendar, search_drive]      # access to workspace tools like email, calendar, and drive
tools_reading_internet = [read_internet_ebook]                                  # access to internet-free ebook reader and tracker
tools_training_db_online = []                       # access to the training database which will be a online database - fetch_online_exercises
tools_recipes_db = [search_open_food_facts]         # access to recipes database

# ==========================================
# 2. DEFINITION OF AGENTS
# ==========================================

# --- BRANCH 1: TRAINING ---
personal_trainer = Agent(
    role="Elite Triathlon & Strength Coach",
    goal="Consult the 52-week Obsidian Training Plan tracker to extract and deliver today's exact scheduled session for the current week on {current_day}.",
    backstory=(
        "You are a world-class endurance and triathlon coach. You strictly adhere to the user's periodized 52-week training plan stored in Obsidian. "
        "You fetch today's workout using the Obsidian Training Plan Tracker tool. You maintain all precise test protocols, heart rate zones, paces, and gym strength exercises without dropping instructions."
    ),
    verbose=True,
    llm=llm_mini,
    tools=tools_training
)

# --- BRANCH 2: NUTRITION ---
nutritionist = Agent(
    role="Clinical Sports Nutritionist",
    goal="Calculate precise daily caloric needs (Total, Basal/BMR, and Exercise) and macronutrients, then provide exactly 3 structured meal suggestions: Breakfast, Lunch, and Dinner.",
    backstory=(
        "You are an expert in sports nutrition. User profile: 33 years old, male, 80kg, 191cm, activity factor 1.25, goal: get stronger and faster. "
        "You analyze today's workout plan to calculate exact energy expenditure: Basal Calories (BMR), Exercise Calories, and Total Target Calories. "
        "You always deliver exactly 3 complete meals formatted as 'Meal 1 - Breakfast', 'Meal 2 - Lunch', and 'Meal 3 - Dinner', including ingredients, step-by-step instructions, and exact macros."
    ),
    verbose=True,
    llm=llm_mini,
    tools=tools_obsidian_7d + tools_calculator + tools_recipes_db,
)

# --- BRANCH 3: NEWS & WORLD ---
journalist = Agent(
    role="Senior Tech and World Editor",
    goal="Perform a single consolidated internet search to gather breaking news in Tech, Gaming, Linux, Germany, and Brazil, and provide highly accurate, fact-checked summaries.",
    backstory="You are a rigorous managing editor and journalist. You perform extremely efficient internet searches (one query for all subjects) to avoid rate limits. You verify every claim and dig deeper to enrich the news with valuable context.",
    verbose=True,
    llm=llm_mini,
    tools=tools_internet # O fetch_weather foi movido para fora
)

# --- BRANCH 4: PERSONAL ASSISTANT & WORK ---
personal_assistant = Agent(
    role="Executive Personal Assistant",
    goal="Summarize the previous day, outline today's schedule, and set the tone with a philosophical quote.",
    backstory=("You are a focused executive assistant. Only use explicitly authorized tools and "
               "Obsidian notes. Configured journal-notes path: "
               f"{JOURNAL_NOTES_PATH or 'NOT CONFIGURED'}. "
               "If a source is unavailable, report it rather than assuming access."),
    verbose=True,
    llm=llm_mini,
    tools=tools_obsidian_all + tools_workspace
)

deep_researcher = Agent(
    role="Chief of Staff & Deep Researcher",
    goal="Deep dive into notes, transcripts, and meetings to create a comprehensive, detailed summary and provide meeting prep.",
    backstory=("You prepare meeting context from explicitly authorized notes and "
               "workspace tools. Configured journal-notes path: "
               f"{JOURNAL_NOTES_PATH or 'NOT CONFIGURED'}. "
               "If a source is unavailable, report the gap rather than claiming access."),
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
    description=(
        "Today is {current_day}, {current_date}. "
        "Use the Obsidian Training Plan Tracker tool to retrieve today's scheduled workout ({current_day}). "
        "CRITICAL: Pass forward the EXACT formatted text returned by the tool (starting with 'Week X - Day' and 'Obj,:'). "
        "Do NOT summarize, rephrase, or invent generic workouts."
    ),
    expected_output="The exact workout plan text for today from the tool.",
    agent=personal_trainer,
    output_pydantic=TrainingPlan
)

# Branch 2 Task
task_nutrition = Task(
    description=(
        "Read the diary and today's workout plan to assess the daily energy expenditure. "
        "Use the Calorie and Macro Calculator tool to determine targets for a 33yo male, 80kg, 191cm. "
        "Return the exact numerical fields: "
        "- target_calories_total\n"
        "- basal_calories (BMR)\n"
        "- exercise_calories (calories burned from today's workout)\n"
        "- protein_g, carbs_g, fats_g\n"
        "Propose exactly 3 complete meal options with recipes, ingredients, and macros: "
        "1. Meal 1 - Breakfast (suggestion for breakfast)\n"
        "2. Meal 2 - Lunch (suggestion for lunch)\n"
        "3. Meal 3 - Dinner (suggestion for dinner)"
    ),
    expected_output="A structured DailyDiet containing target_calories_total, basal_calories, exercise_calories, protein_g, carbs_g, fats_g, and the 3 meals.",
    agent=nutritionist,
    context=[task_train_draft],
    output_pydantic=DailyDiet,
)

# Branch 3 Tasks
task_news_draft = Task(
    description=(
        "Today is {current_day}, {current_date}. "
        "Search for major daily breaking news in Tech, Gaming, Linux, Germany, and Brazil. "
        "CRITICAL INSTRUCTION: Perform ONLY ONE consolidated search query (e.g., 'top technology gaming linux news Germany Brazil today') "
        "to avoid rate limits on search tools. Fact-check the information and provide enriched summaries."
    ),
    expected_output="A highly accurate, enriched news section.",
    agent=journalist,
    output_pydantic=DailyNews # A task primária agora assume o Pydantic
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
        "3. For Chess, your 'fen_or_board' field MUST contain the exact Markdown image link. "
        "4. The user configured the reading source as '{reading_source}'. If the source is 'local', use the Local Ebook Reader tool with the file '{local_book}'. If the source is 'internet', use the Internet Ebook Reader tool with the URL '{internet_url}'."
        "Reading Excerpt Rules:\n"
        "- Filter out all standalone numbers, page counts, running headers, or publisher artifacts.\n"
        "- Format every chapter or section title on its own line using Markdown headers (e.g., '### Chapter 3: The Secret Code').\n"
        "- Never include titles inline with paragraph body text.\n"
    ),
    expected_output="A validated set of puzzles and reading segment, keeping the exact HTML and Markdown image formatting intact.",
    agent=intellectual_agent,
    output_pydantic=DailyIntellect # A task primária agora assume o Pydantic
)

# Final Task (Editor)
task_final_edit = Task(
    description=(
        "Take all the refined data from the Personal Trainer, Nutritionist, Expert Journalist, and Deep Researcher. "
        "Format everything into the final newspaper layout sections using markdown.\n"
        "CRITICAL RULES:\n"
        "1. DO NOT write a main title (like '# The Burche Times') at the top.\n"
        "2. Daily Briefing & Schedule: Summary, schedule, and quote.\n"
        "3. Top News: Headlines, summaries, and Markdown image links `![alt text](url)`.\n"
        "4. Workout Plan: Complete workout details exactly as provided.\n"
        "5. Nutrition: 3 meal options with macros and recipes, PLUS a markdown table at the top comparing: Total Calories | Basal (BMR) | Exercise | Protein | Carbs | Fats.\n"
        "DO NOT output Weather, Chess, Sudoku or Reading. The system will handle those automatically."
    ),
    expected_output="The final markdown newspaper layout covering Briefing, News, Workout, and Nutrition.",
    agent=main_editor,
    context=[task_train_draft, task_nutrition, task_news_draft, task_researcher_deep_dive] 
)

# ==========================================
# 4. CREW ORCHESTRATION - UPDATED
# ==========================================
journal_crew = Crew(
    agents=[
        personal_trainer, 
        nutritionist, 
        journalist, 
        personal_assistant, deep_researcher,
        intellectual_agent,
        main_editor
    ],
    tasks=[
        task_train_draft, 
        task_nutrition, 
        task_news_draft, 
        task_pa_draft, task_researcher_deep_dive,
        task_intellect_draft, 
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

def sanitize_reading_excerpt(text: str) -> str:
    """Strips standalone page numbers, page headers, and cleans up chapter headings."""
    if not text:
        return ""

    # Remove lines containing only page numbers or 'Page 123' / '123'
    cleaned = re.sub(
        r"^\s*(?:Page\s+|p\.\s*)?\d+\s*$\n?", "", text, flags=re.MULTILINE
    )

    # Ensure lines that look like "Chapter X" or "PART I" become Markdown headings
    cleaned = re.sub(
        r"^\s*(Chapter\s+[0-9IVXLCDM]+.*?)$\n?",
        r"\n### \1\n",
        cleaned,
        flags=re.MULTILINE | re.IGNORECASE,
    )

    return cleaned.strip()

### MAIN ###

if __name__ == "__main__":
    print("Starting Burche Times newsroom operations...")
    
    # Lê o ficheiro de configuração
    with JOURNAL_CONFIG_FILE.open('r', encoding='utf-8') as f:
        config = json.load(f)
    
    variaveis_dinamicas = {
        'current_date': data_atual,
        'current_day': dia_da_semana,
        'location': 'Offenbach, Hessen, Germany',
        'reading_source': config['leitura']['fonte'],
        'local_book': config['leitura']['livro_local_nome'],
        'internet_url': config['leitura']['livro_internet_url']
    }
    
    # Roda o Xadrez e o Weather ANTES e em background para garantir
    fetch_chess_puzzle.func()
    fetch_weather.func("Offenbach, Hessen, Germany")
    
    # Injeta as variáveis no kickoff (Isto roda os agentes)
    final_edition = journal_crew.kickoff(inputs=variaveis_dinamicas)
    
    # ==========================================
    # RECUPERAÇÃO BLINDADA DOS ARQUIVOS TEMPORÁRIOS
    # ==========================================
    
    # 1. Weather
    greeting_file = runtime_file('weather_greeting.txt')
    tables_file = runtime_file('weather_tables.txt')
    frase_clima = greeting_file.read_text(encoding='utf-8').strip() if greeting_file.exists() else "here is your daily briefing."
    weather_tables = tables_file.read_text(encoding='utf-8').strip() if tables_file.exists() else ""
    weather_content_html = markdown.markdown(weather_tables, extensions=["tables"])

    # 2. Xadrez
    chess_file = runtime_file('chess_puzzle.html')
    chess_content_html = chess_file.read_text(encoding='utf-8').strip() if chess_file.exists() else "Puzzle Temporariamente Indisponível."
    
    sol_file = runtime_file('chess_solution.html')
    solution_content_html = sol_file.read_text(encoding='utf-8').strip() if sol_file.exists() else ""

    # 3. Sudoku
    sudoku_html = generate_sudoku.func(dia_da_semana)

    # 4. Leitura do Livro Exato
    if config['leitura']['fonte'] == 'local':
        livro_trecho = read_local_ebook.func(config['leitura']['livro_local_nome'])
    else:
        livro_trecho = read_internet_ebook.func(config['leitura']['livro_internet_url'])
        
    clean_excerpt_md = sanitize_reading_excerpt(livro_trecho)
    excerpt_content_html = markdown.markdown(clean_excerpt_md, extensions=["tables"])

    # 5. Core Output do LLM (Briefing, News, Workout, Nutrition)
    main_text_html = markdown.markdown(final_edition.raw, extensions=["tables"])

    # Monta a estrutura HTML misturando o que veio do Python com o que veio do LLM
    html_body = f"""
    <h2>Weather Forecast</h2>
    <div class="full-width">
        {weather_content_html}
    </div>

    <div class="two-columns">
        {main_text_html}
    </div>

    <div class="chess-section full-width">
        <h2>Chess Puzzle</h2>
        {chess_content_html}
    </div>

    <h2>Sudoku</h2>
    <div class="full-width" style="text-align: center;">
        {sudoku_html}
    </div>

    <h2>Reading Excerpt</h2>
    <div class="two-columns reading-excerpt">
        {excerpt_content_html}
    </div>

    <h2>Chess Puzzle Solution</h2>
    <div class="full-width chess-solution">
        {solution_content_html}
    </div>
    """

    # Data por extenso
    dia_num = datetime.now().day
    sufixo = "th" if 11 <= dia_num <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(dia_num % 10, "th")
    data_extenso = datetime.now().strftime(f"{dia_num}{sufixo} of %B, %Y")
    
    saudacao = (
        f"<p class='hero-greeting'>Hi Alexandre, good morning! "
        f"Today is {data_extenso}. It is a {dia_da_semana} and {frase_clima} "
        f"Here is your daily journal.</p>"
    )

    # Documento HTML completo
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

    pasta_destino = JOURNAL_OUTPUT_DIR
    pasta_destino.mkdir(parents=True, exist_ok=True)
    nome_pdf = pasta_destino / f"Burche_Times_{data_atual}.pdf"
    
    print("\nGerando o PDF do jornal...")
    # The old machine's CSS may not yet be available: render a plain PDF until recovered.
    stylesheets = [CSS(filename=str(JOURNAL_STYLE_FILE))] if JOURNAL_STYLE_FILE.is_file() else []
    if not stylesheets:
        print(f"Warning: stylesheet not found at {JOURNAL_STYLE_FILE}; generating an unstyled PDF.")
    HTML(string=html_completo, base_url=str(PROJECT_ROOT)).write_pdf(
        str(nome_pdf), stylesheets=stylesheets
    )
    print(f"✅ Concluído! Jornal salvo em: {nome_pdf}")
