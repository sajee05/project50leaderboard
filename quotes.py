"""Random UPSC-flavoured line for the weekly / monthly posts: classic maxims and thinkers, plus UPSC reminders. Each entry is (kind, text, who)."""
import random

LINES = [
    # ancient maxims and thinkers
    ("Maxim", "You have a right to your actions, but never to the fruits of your actions.", "Bhagavad Gita 2.47"),
    ("Maxim", "Work gets done by effort, not by wishes.", "Hitopadesha"),
    ("Maxim", "Dripping water hollows out the stone.", "Ovid"),
    ("Maxim", "The obstacle in the path becomes the path.", "Marcus Aurelius"),
    ("Maxim", "A journey of a thousand miles begins with a single step.", "Lao Tzu"),
    ("Maxim", "It does not matter how slowly you go, so long as you do not stop.", "attributed to Confucius"),
    ("Maxim", "It is not that we have a short time to live, but that we waste much of it.", "Seneca"),
    ("Maxim", "Fortune favours the bold.", "Latin proverb"),
    ("Maxim", "The beginning is the most important part of the work.", "Plato"),
    ("Maxim", "However long the night, the dawn will break.", "African proverb"),
    ("Maxim", "Where there is a will, there is a way.", "English proverb"),
    ("Maxim", "Knowing is not enough; we must apply. Willing is not enough; we must do.", "Goethe"),
    ("Maxim", "Learning without thought is labour lost; thought without learning is perilous.", "Confucius"),
    ("Maxim", "Well begun is half done.", "Aristotle"),
    ("Maxim", "As you sow, so shall you reap.", "Galatians 6:7"),
    ("Maxim", "One who conquers himself is greater than one who conquers a thousand in battle.", "Dhammapada"),
    ("Maxim", "A king's happiness lies in the happiness of his subjects.", "Kautilya, Arthashastra (paraphrased)"),
    ("Maxim", "Rise, awake, and stop not till the goal is reached.", "Swami Vivekananda (Katha Upanishad)"),
    ("Maxim", "Character is destiny.", "Heraclitus"),
    ("Maxim", "Do not seek to follow in the footsteps of the wise; seek what they sought.", "Matsuo Basho"),
    # UPSC motivation
    ("UPSC", "Prelims is a lottery only for those who didn't buy enough tickets. Buy more tickets: revise.", ""),
    ("UPSC", "Nobody remembers the hours you studied. The rank list remembers.", ""),
    ("UPSC", "The syllabus is vast, which is exactly why a steady daily hour beats a heroic Sunday.", ""),
    ("UPSC", "Consistency is the only optional subject everyone gets to choose.", ""),
    ("UPSC", "Today's tired is tomorrow's 'I'm so glad I sat through it'.", ""),
    ("UPSC", "Every PYQ you solve is a free peek at the examiner's mind. Take the peek.", ""),
    ("UPSC", "A good answer is one idea, one example, one conclusion. Stop writing a novel.", ""),
    ("UPSC", "Rank 1 and rank 1000 both started with an open book and a wandering mind.", ""),
    ("UPSC", "Mock tests are cheap failures. Take them now so the real exam can be dull.", ""),
    ("UPSC", "Forget 'motivated'. Be 'seated at the desk by 6' and let the rest follow.", ""),
]


def pick(seed=None):
    k, text, who = random.Random(seed).choice(LINES) if seed is not None else random.choice(LINES)
    return k, text, who


def block(seed=None):
    """HTML snippet for a Telegram caption: just the line, in italics, with who said it."""
    import html
    _, text, who = pick(seed)
    return f"<i>{html.escape(text)}</i>" + (f" — {html.escape(who)}" if who else "")
