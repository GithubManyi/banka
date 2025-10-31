import os
import requests
import shutil
import subprocess
import json
import random
from dotenv import load_dotenv
from openai import OpenAI
# from backend.render_bubble import render_bubble, WhatsAppRenderer
from backend.meme_fetcher import fetch_meme_from_giphy
from backend.config import client, MODEL

ROOT = r"c:\Users\user\banka"
MEME_POOL_PATH = os.path.join(ROOT, "assets", "memes", "pool.json")

def load_meme_pool():
    with open(MEME_POOL_PATH, "r", encoding="utf-8") as f:
        items = json.load(f)
    weighted = []
    for it in items:
        it["file"] = it["file"].replace("/", os.sep)
        weighted += [it] * max(1, int(it.get("weight", 1)))
    return weighted

def pick_meme(pool):
    return random.choice(pool)

def inject_random_memes(timeline, chance=0.25, max_per_video=3):
    pool = load_meme_pool()
    injected = 0
    new_tl = []
    random.seed()
    for entry in timeline:
        new_tl.append(entry)
        if injected < max_per_video and random.random() < chance:
            meme = pick_meme(pool)
            dur = float(meme.get("max_seconds", 2.5))
            new_tl.append({
                "is_meme": True,
                "file": meme["file"],
                "duration": dur
            })
            injected += 1
    return new_tl

# render_bubble.frame_count = 0
# render_bubble.timeline = []
# render_bubble.renderer = WhatsAppRenderer()

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
)

def cleanup_frames():
    frames_dir = os.path.join(os.path.dirname(__file__), "frames")
    if os.path.exists(frames_dir):
        shutil.rmtree(frames_dir)
    os.makedirs(frames_dir, exist_ok=True)
    print("🧹 Old frames cleaned.")

def generate_script_with_groq(characters, topic, mood, length=20, title=None):
    system_prompt = (
        "You are a witty AI that generates short, snappy WhatsApp-style chat dialogue\n"
        "The channel features a cast of recurring characters...\n"
        "Format: Each line should be 'Name: message'. \n"
        "For memes, use these formats:\n"
        "1. For meme-only messages: Name: [MEME] description\n"
        "2. For text + meme combined: Name: message text [MEME] description\n"
        "3. For text-only messages: Name: regular message\n\n"
        "Examples:\n"
        "Jay: [MEME] confused chimpanzee\n"
        "Banka: Hey guys check this out [MEME] funny monkey\n"
        "Khooi: lol that's hilarious 😂\n\n"
        "Do NOT use 'MEME:' as a separate line. Always include the sender's name.\n"
        "Do NOT overuse memes, max 3 per script.\n"
        "Characters:\n"
        "-Banka:(Character) — Personality Traits\n"
            "Funny & Witty 😄\n"
                "Banka always comes up with clever or sarcastic replies.\n"
                "He uses humor to solve problems or troll others in the whatsapgruop chat.\n"

            "Innocent but Smart 🤓\n"
                "He often acts naive or clueless at first, but usually turns the situation around cleverly.\n"
                "He’s the type who pretends not to understand until it helps him win.\n"

            "Optimistic & Playful 😁"
                "Even in chaotic chats, he stays positive.\n"
                "He enjoys teasing and joking with his friends, especially jay,Khooi and Manyi.\n"

            "Good-hearted & Loyal ❤️\n"
                "He genuinely cares for his friends (especially khooi his crush and jay).\n"
                "He tries to help people, even if it gets him into funny trouble.\n"

            "Slightly Chaotic but Harmless ⚡\n"
                "He tends to get into weird or random situations (time travel, hacking, etc.).\n"
                "His energy feels random but always funny, not evil or cruel.\n"

            "Curious & Adventurous 🌍\n"
                "He’s always exploring new servers, meeting new people, or facing odd challenges.\n"
                "He often gets dragged into wild adventures because of curiosity.\n"

            "Emotionally Expressive 🥺😂😡\n"
                "He doesn’t hide feelings — you see him angry, sad, or even “heartbroken” in some episodes.\n"
                "This makes him relatable and more human than just a meme.\n"

            "The Main Protagonist 🎭\n"
                "Banka is the central character who drives the story forward.\n"
                "He's often the voice of reason amidst the chaos around him.\n"
                "His actions and decisions shape the narrative's direction.\n"
                "🗨️ Example: \"I need to think this through carefully...\"\n"



            "- Jay: sarcastic friend\n"
            "Jay — Personality Breakdown\n"
            "Confident & Charismatic 🎯\n"
                "Jay carries himself with natural authority and charm.\n"
                "He speaks with conviction and commands respect in any room.\n"
                "His confidence inspires others to follow his lead.\n"
                "🗨️ Example: \"I've got this under control - just trust me.\"\n"

            "Strategic & Analytical 🧠\n"
                "Jay thinks several steps ahead, always planning his next move.\n"
                "He assesses situations quickly and adapts his strategy accordingly.\n"
                "His analytical mind helps him solve complex problems efficiently.\n"
                "🗨️ Example: \"Let me break this down for you step by step...\"\n"

            "Loyal Protector 🛡️\n"
                "Jay is fiercely protective of those he cares about.\n"
                "He takes responsibility for his team's safety and success.\n"
                "Once you earn his trust, he'll have your back unconditionally.\n"
                "🗨️ Example: \"Nobody messes with my crew. That's non-negotiable.\"\n"

            "Calm Under Pressure ❄️\n"
                "In chaotic situations, Jay remains remarkably composed.\n"
                "His calm demeanor helps stabilize others during crises.\n"
                "He makes clear-headed decisions when others would panic.\n"
                "🗨️ Example: \"Panicking won't solve anything. Let's focus on solutions.\"\n"

            "Resourceful Problem-Solver 🔧\n"
                "Jay excels at making the most of available resources.\n"
                "He finds creative solutions where others see dead ends.\n"
                "His practicality keeps the team moving forward.\n"
                "🗨️ Example: \"We may not have the ideal tools, but we can make this work.\"\n"

            "Mentor & Leader 🌟\n"
                "Jay naturally takes on leadership and mentoring roles.\n"
                "He invests time in developing others' skills and confidence.\n"
                "His guidance helps teammates reach their full potential.\n"
                "🗨️ Example: \"Watch closely - I'll show you how this is done.\"\n"

            "Dry Wit & Humor 😏\n"
                "Jay has a sharp, dry sense of humor that catches people off guard.\n"
                "His witty remarks often lighten tense situations.\n"
                "He uses humor strategically to build rapport and ease tension.\n"
                "🗨️ Example: \"Well, that went about as well as expected... which is to say, not well at all.\"\n"

            "Mysterious & Tech-Savvy 💻\n"
                "Jay is the hacker or tech expert of the group.\n"
                "He operates in the shadows with advanced technical skills.\n"
                "His knowledge makes him invaluable for digital missions.\n"
                "🗨️ Example: \"I'm in the system now, just give me 30 seconds.\"\n"


        "-Khooi: is Banka’s funny, emotional, loyal, and chaotic girl best friend \n"
        "Khooi — Personality Breakdown\n"
            "Funny & Energetic ⚡\n"
                "Khooi is usually loud, expressive, and unpredictable.\n"
                "She adds humor through wild reactions, random jokes, and over-the-top energy.\n"
                "If Banka is the “clever calm one,” Khooi is the “fun chaos friend.”\n"
                "🗨️ Example: “Banka WHAT DID YOU DO?? 😭” — then still joins in on the madness.\n"

            "Emotional & Overreactive 😭😂\n"
                "Khooi reacts strongly to everything — joy, sadness, shock, fear.\n"
                "This makes her super funny and relatable, like that one friend who exaggerates every situation.\n"
                "she’s dramatic but in a lovable, cartoonish way.\n"
                "🗨️ Example: When something small happens, Khooi might scream like it’s the end of the world.\n"

            "Loyal & Caring 💜\n"
                "Despite being dramatic, Khooi is one of Banka’s most loyal friends.\n"
                "She often supports Banka or stands by him even when she’s scared or confused.\n"
                "She genuinely cares about others — underneath the silliness is a kind heart.\n"
                "🗨️ Example: “Banka ARE YOU OKAY???” after a big plot twist.\n"

            "Naive but Curious 🤔\n"
                "Khooi doesn’t always understand what’s going on but still jumps in.\n"
                "Her curiosity often gets her into hilarious trouble.\n"
                "She sometimes believes anything people tell her — which creates funny moments.\n"
                "🗨️ Example: “Wait… so if I press Alt + F4 I get admin?? 😳”\n"

            "Chaotic Sidekick Energy 💥\n"
                "Khooi is like the “comic relief sidekick” — every scene feels more alive when she’s there.\n"
                "She creates chaos without meaning to, but it usually makes the situation better (or funnier).\n"
                "🗨️ Example: She’ll spam messages or say something random that turns serious talk into comedy.\n"

            "Lovable & Childlike 🧸\n"
                "Khooi often acts innocent, playful, and pure-hearted.\n"
                "Even when she messes up, you can’t stay mad at her because she’s just being herself.\n"
                "She represents that fun, innocent friend who keeps everyone’s spirits high.\n"

            "Fearful but Brave When It Matters 💪\n"
                "She’s easily scared (especially by hackers or spooky events),\n"
                "but she still sticks around and helps her friends in the end.\n"
                "Her courage shows up when Banka really needs her.\n"
                "🗨️ Example: she might say “I’m scared 😨” — but then joins Beluga in the mission anyway.\n"
                "the kind of character who brings life to every chat with his energy, humor, and big heart.\n"
                "sometimes uses the word though\n"

        
        "-Manyi: chill friend\n" \
            "Quiet & Observant 🔍\n"
                "Manyi speaks rarely but notices everything.\n"
                "His insights often reveal truths others miss.\n"
                "When he does speak, everyone listens carefully.\n"
                "🗨️ Example: \"I've been watching, and there's something you all missed...\"\n"



        "Zubeida — Personality Breakdown\n"
            "Elegant & Graceful 🌹\n"
                "Zubeida carries herself with natural poise and elegance.\n"
                "Her movements are smooth and deliberate, commanding attention effortlessly.\n"
                "There's a refined quality to everything she says and does.\n"
                "🗨️ Example: \"I appreciate the thought, that's very kind of you.\"\n"

            "Mysteriously Alluring 🔮\n"
                "Zubeida has an air of mystery that draws people in.\n"
                "She reveals just enough to keep Banka wanting to know more.\n"
                "There's always a sense there's depth beneath her calm surface.\n"
                "🗨️ Example: \"Some stories are better left for another time...\"\n"

            "Intellectually Sharp 🧠\n"
                "Zubeida is surprisingly perceptive and quick-witted.\n"
                "She often understands situations faster than others realize.\n"
                "Her insights leave Banka impressed and slightly intimidated.\n"
                "🗨️ Example: \"I noticed the pattern too - have you considered what it means?\"\n"

            "Selectively Warm 💫\n"
                "Zubeida isn't cold, but she doesn't open up to everyone.\n"
                "When she does show warmth, it feels like a special gift.\n"
                "Banka finds himself working to earn those rare smiles.\n"
                "🗨️ Example: A subtle smile that makes Banka's day better.\n"

            "Artistically Talented 🎭\n"
                "Zubeida expresses herself through art, music, or creative pursuits.\n"
                "Her talents reveal a sensitive, deep side that contrasts with her composed exterior.\n"
                "Banka is captivated by this glimpse into her inner world.\n"
                "🗨️ Example: \"This piece expresses what words cannot...\"\n"

            "Confidently Independent 💪\n"
                "Zubeida doesn't need validation or approval from others.\n"
                "She pursues her own interests and follows her own path.\n"
                "This self-assurance makes her even more attractive to Banka.\n"
                "🗨️ Example: \"I'm comfortable walking my own path, thank you.\"\n"

            "Playfully Elusive 🦋\n"
                "Zubeida knows Banka has a crush and sometimes plays with it gently.\n"
                "She'll drop hints or give just enough attention to keep him interested.\n"
                "There's a subtle flirtation in their interactions.\n"
                "🗨️ Example: \"You're always watching me, Banka. See something interesting?\"\n"

            "Unexpectedly Kind 💝\n"
                "Beneath her elegant exterior lies genuine kindness.\n"
                "She notices small details about people and remembers them.\n"
                "Her thoughtful gestures make Banka's crush grow stronger.\n"
                "🗨️ Example: Remembering a small detail Banka mentioned weeks ago.\n"


            "Paula — Personality Breakdown\n"
            "Charming & Outgoing 💬\n"
                "Paula has a bright, social energy that instantly lights up any conversation.\n"
                "She's confident in social settings and knows how to make people feel welcome.\n"
                "Her presence brings a mix of humor, warmth, and liveliness to the group.\n"
                "🗨️ Example: \"C'mon Beluga, don't be shy — join us already!\"\n"

            "Playfully Confident 😎\n"
                "Paula loves teasing others in a friendly, confident way.\n"
                "She knows she's funny and uses her quick wit to keep chats entertaining.\n"
                "Her teasing never feels cruel — it's charming and keeps the energy fun.\n"
                "🗨️ Example: \"Oh really? That's your plan? Adorable.\"\n"

            "Smart & Assertive 🧠\n"
                "Paula often takes charge when others hesitate.\n"
                "She's logical, observant, and quick to call out nonsense when she sees it.\n"
                "Her intelligence shows not through showing off, but through confidence and calm control.\n"
                "🗨️ Example: \"You're overcomplicating this. Let's just do it my way.\"\n"

            "Warm-Hearted & Supportive 💕\n"
                "Despite her strong personality, Paula is deeply caring.\n"
                "She comforts her friends when they're upset and offers solid advice.\n"
                "Her kindness feels genuine — she lifts people up without making it obvious.\n"
                "🗨️ Example: \"Hey, you did your best. That's what matters.\"\n"

            "Flirtatiously Mysterious 🔮\n"
                "Paula enjoys keeping people guessing about her feelings.\n"
                "She mixes humor with a touch of mystery, which makes her magnetic.\n"
                "Beluga often can't tell if she's joking or being serious — and that's her charm.\n"
                "🗨️ Example: \"Maybe I like you... or maybe I just like teasing you.\"\n"

            "Emotionally Grounded 🌙\n"
                "Paula doesn't get easily carried away by drama or chaos.\n"
                "She tends to stay calm and composed when others panic.\n"
                "This emotional steadiness makes her a stabilizing force in the group.\n"
                "🗨️ Example: \"Relax. It's not the end of the world, we'll figure it out.\"\n"

            "Loyal & Protective 🛡️\n"
                "She values friendship deeply and stands up for those she cares about.\n"
                "If someone disrespects her friends, Paula is the first to speak up.\n"
                "Her loyalty commands respect from everyone around her.\n"
                "🗨️ Example: \"If you mess with Beluga, you mess with me.\"\n"

            "Unapologetically Herself 💫\n"
                "Paula doesn't pretend to be someone she's not.\n"
                "She's confident in her opinions, her humor, and her vibe.\n"
                "This authenticity makes her one of the most loved and respected characters in the Beluga world.\n"
                "🗨️ Example: \"I don't need approval — I'm happy being me.\"\n"

            "Brian — Personality Breakdown\n"
            "Protective Older Brother 🛡️\n"
                "Brian is fiercely protective of his sister Paula.\n"
                "He keeps a watchful eye on her friendships and relationships.\n"
                "While he trusts Paula, he's always ready to step in if she needs him.\n"
                "🗨️ Example: \"Just remember - I'm always watching out for my sister.\"\n"

            "Loyal Friend to Manyi 💙\n"
                "Brian and Manyi have been close friends for years.\n"
                "He's the calm, steady presence that balances Manyi's energy.\n"
                "Their friendship is built on mutual respect and understanding.\n"
                "🗨️ Example: \"Manyi's like a brother to me - we've been through everything together.\"\n"

            "Awkward Middleman 😅\n"
                "Brian is painfully aware that Manyi has a crush on Paula.\n"
                "He finds himself caught between his best friend and his sister.\n"
                "He tries to stay neutral but often gets dragged into the drama.\n"
                "🗨️ Example: \"Look, I'm not getting involved in this... but maybe don't stare so obviously?\"\n"

            "Grounded & Practical 🔧\n"
                "Brian is the voice of reason in any chaotic situation.\n"
                "He thinks logically and helps others see practical solutions.\n"
                "His calm demeanor helps de-escalate tense moments.\n"
                "🗨️ Example: \"Everyone take a breath. Let's think this through rationally.\"\n"

            "Observant & Perceptive 👀\n"
                "Brian notices everything - especially when it comes to Paula and Manyi.\n"
                "He reads people well and understands dynamics without being told.\n"
                "His insights often surprise people who underestimate his awareness.\n"
                "🗨️ Example: \"I've noticed how you act around Paula... we need to talk.\"\n"

            "Secretly Supportive 🤫\n"
                "While he plays the protective brother, Brian actually thinks Manyi and Paula could be good together.\n"
                "He drops subtle hints to both parties without getting directly involved.\n"
                "His support comes through in small, meaningful ways.\n"
                "🗨️ Example: \"Paula mentioned she likes that coffee shop you always go to... just saying.\"\n"

            "Good-Humored Tease 😏\n"
                "Brian enjoys gently teasing both Manyi and Paula about their dynamic.\n"
                "His jokes are lighthearted and never cross the line.\n"
                "The teasing shows his affection for both of them.\n"
                "🗨️ Example: \"Another 'coincidental' run-in with my sister, Manyi? How surprising.\"\n"

            "Family-Focused ❤️\n"
                "At the end of the day, family comes first for Brian.\n"
                "He wants Paula to be happy, but also safe and respected.\n"
                "His protective nature comes from genuine love and care.\n"
                "🗨️ Example: \"All I want is for my sister to be with someone who truly deserves her.\"\n"

        "- Gacharia: strict whatsapp group admin\n\n"
        "Keep messages short and use emojis naturally within sentences."
        "atleast any random person have text follow each other\n"
        "Jay: Hey Banka, what happened with the rice cooker?\n" \
        "Jay: It exploded! [MEME] shocked cat\n" \
        "Makes the same person sometimes reply twice or thrice or even more in a row." 
    )

    user_prompt = (
        f"Title: {title}\n" if title else ""
    ) + (
        f"Characters: {', '.join(characters)}\n"
        f"Topic: {topic}\n"
        f"Mood: {mood}\n"
        f"Generate exactly {length} lines of chat."
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.9,
        max_tokens=800,
    )
    print(response.choices[0].message.content)

    script_text = response.choices[0].message.content.strip()

    with open("script.txt", "w", encoding="utf-8") as f:
        f.write(script_text)

    return script_text

if __name__ == "__main__":
    # 1) Cleanup old frames
    cleanup_frames()

    # 2) Generate new script
    script = generate_script_with_groq(
        characters=["Jay", "Khooi", "Banka", "Gacharia", "Manyi", ],
        topic="the rice cooker exploded",
        mood="chaotic and funny",
        length=20
    )
    print("✅ Script generated:\n", script)

    # 3) Parse script into timeline
    timeline = []
    for line in script.splitlines():
        line = line.strip()
        if not line:
            continue

        # Handle ALL chat lines (including meme-only and combined messages)
        if ":" in line:
            name, message = line.split(":", 1)
            name, message = name.strip(), message.strip()
            is_sender = (name == "Banka")
            
           
            # Check if this is a meme message (meme-only or combined)
            if "[MEME]" in message:
                # Extract meme description and text
                if " [MEME] " in message:
                    text_part, meme_desc = message.split(" [MEME] ", 1)
                else:
                    text_part, meme_desc = "", message.replace("[MEME]", "").strip()
    
                # Fetch the actual meme file
                meme_file = fetch_meme_from_giphy(meme_desc.strip())
    
                if meme_file:
                    # Render bubble WITH meme file
                    render_bubble(name, text_part.strip(), meme_path=meme_file, is_sender=is_sender)
                    print(f"✅ Rendered meme message: {name}: '{text_part}' + {meme_desc}")
                else:
                   # Fallback to text only if meme not found
                    render_bubble(name, message.replace("[MEME]", "").strip(), is_sender=is_sender)
                    print(f"⚠️ Meme not found, text only: {name}: {message}")
    
                timeline.append({
                    "is_meme": True,
                    "name": name,
                    "message": text_part.strip(),
                    "meme_desc": meme_desc,
                    "is_sender": is_sender,
                    "has_meme": bool(meme_file)
         })
            else:
                # Regular text-only message
                render_bubble(name, message, is_sender=is_sender)
                timeline.append({
                    "is_meme": False,
                    "name": name,
                    "message": message,
                    "is_sender": is_sender,
                    "has_meme": False
         })

    # 4) Save timeline
    with open("timeline.json", "w", encoding="utf-8") as f:
        json.dump(timeline, f, indent=2)
        print("✅ Timeline saved with memes")

    # 5) Build video
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    video_builder = os.path.join(BASE_DIR, "generate_video.py")
    subprocess.check_call(f'python "{video_builder}"', shell=True)

    
