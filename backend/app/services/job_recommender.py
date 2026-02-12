"""
Job Recommendation Service

Generates intelligent job recommendations based on resume analysis.
Extracts skills, role titles, experience level, technologies, and domain
keywords from resume text, then matches against a curated job database
to produce ranked recommendations with match percentages.

No paid APIs or live scraping — all job data is simulated realistically.
"""

import re
import logging
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ── Experience Level Detection ──────────────────────────────────────────────

_EXPERIENCE_PATTERNS = {
    "intern": re.compile(
        r"\b(intern|internship|co-?op|trainee|apprentice)\b", re.IGNORECASE
    ),
    "entry": re.compile(
        r"\b(entry[- ]level|junior|associate|new\s+grad|recent\s+graduate|0[- ]?[12]\s+years?)\b",
        re.IGNORECASE,
    ),
    "mid": re.compile(
        r"\b(mid[- ]?level|mid[- ]?senior|[2-5]\+?\s+years?)\b", re.IGNORECASE
    ),
    "senior": re.compile(
        r"\b(senior|sr\.?|lead|principal|staff|[5-9]\+?\s+years?|10\+?\s+years?)\b",
        re.IGNORECASE,
    ),
    "manager": re.compile(
        r"\b(manager|director|head\s+of|vp|vice\s+president|chief|c-level|cto|cio)\b",
        re.IGNORECASE,
    ),
}


def _detect_experience_level(text: str) -> str:
    """Detect experience level from resume text. Returns one of:
    intern, entry, mid, senior, manager. Defaults to 'mid'."""
    # Check from most senior to least — return highest detected
    for level in ["manager", "senior", "mid", "entry", "intern"]:
        if _EXPERIENCE_PATTERNS[level].search(text):
            return level
    return "mid"


# ── Skill/Domain Extraction ────────────────────────────────────────────────

# Comprehensive skill categories for matching
SKILL_CATEGORIES = {
    "languages": {
        "python", "javascript", "typescript", "java", "c++", "c#", "go", "golang",
        "rust", "ruby", "php", "swift", "kotlin", "scala", "r", "matlab", "perl",
        "dart", "lua", "haskell", "elixir", "clojure", "objective-c", "shell",
        "bash", "powershell", "sql", "html", "css", "sass", "less",
    },
    "frameworks": {
        "react", "angular", "vue", "svelte", "next.js", "nextjs", "nuxt",
        "django", "flask", "fastapi", "spring", "spring boot", "express",
        "node.js", "nodejs", "rails", "ruby on rails", "laravel", "asp.net",
        ".net", "dotnet", "flutter", "react native", "electron", "qt",
        "tensorflow", "pytorch", "keras", "scikit-learn", "sklearn",
        "pandas", "numpy", "scipy", "matplotlib", "streamlit", "gradio",
    },
    "databases": {
        "postgresql", "postgres", "mysql", "mongodb", "redis", "elasticsearch",
        "sqlite", "oracle", "sql server", "dynamodb", "cassandra", "neo4j",
        "firebase", "supabase", "cockroachdb", "mariadb", "memcached",
    },
    "cloud": {
        "aws", "azure", "gcp", "google cloud", "heroku", "vercel", "netlify",
        "digitalocean", "linode", "cloudflare", "render",
    },
    "devops": {
        "docker", "kubernetes", "k8s", "jenkins", "github actions", "gitlab ci",
        "terraform", "ansible", "puppet", "chef", "ci/cd", "ci cd",
        "prometheus", "grafana", "datadog", "nginx", "apache", "linux",
    },
    "data": {
        "machine learning", "deep learning", "nlp", "natural language processing",
        "computer vision", "data science", "data engineering", "data analysis",
        "big data", "hadoop", "spark", "kafka", "airflow", "etl", "data pipeline",
        "statistics", "a/b testing", "power bi", "tableau", "looker",
    },
    "mobile": {
        "ios", "android", "react native", "flutter", "swift", "kotlin",
        "mobile development", "xcode", "android studio",
    },
    "security": {
        "cybersecurity", "penetration testing", "soc", "siem", "encryption",
        "oauth", "jwt", "authentication", "authorization", "security",
    },
    "design": {
        "figma", "sketch", "adobe xd", "ui/ux", "ux design", "ui design",
        "wireframing", "prototyping", "user research", "design systems",
    },
    "soft_skills": {
        "agile", "scrum", "kanban", "project management", "team leadership",
        "mentoring", "cross-functional", "communication", "problem solving",
    },
}

# Flatten for quick lookup
ALL_SKILLS: Set[str] = set()
for category_skills in SKILL_CATEGORIES.values():
    ALL_SKILLS.update(category_skills)


def _extract_skills(text: str) -> Dict[str, List[str]]:
    """Extract skills from resume text, categorized by type."""
    text_lower = text.lower()
    found: Dict[str, List[str]] = {}

    for category, skills in SKILL_CATEGORIES.items():
        matched = []
        for skill in skills:
            # Use word boundary matching for single words, substring for multi-word
            if " " in skill or "." in skill or "/" in skill:
                if skill in text_lower:
                    matched.append(skill)
            else:
                if re.search(r"\b" + re.escape(skill) + r"\b", text_lower):
                    matched.append(skill)
        if matched:
            found[category] = sorted(matched)

    return found


def _extract_role_signals(text: str) -> List[str]:
    """Extract role-related signals from the resume text."""
    roles = []
    role_patterns = [
        (r"\b(software\s+(?:engineer|developer))\b", "Software Engineer"),
        (r"\b(frontend\s+(?:engineer|developer))\b", "Frontend Developer"),
        (r"\b(backend\s+(?:engineer|developer))\b", "Backend Developer"),
        (r"\b(full[- ]?stack\s+(?:engineer|developer))\b", "Full Stack Developer"),
        (r"\b(devops\s+engineer)\b", "DevOps Engineer"),
        (r"\b(data\s+(?:scientist|analyst|engineer))\b", "Data Professional"),
        (r"\b(machine\s+learning\s+engineer)\b", "ML Engineer"),
        (r"\b(mobile\s+(?:developer|engineer))\b", "Mobile Developer"),
        (r"\b(cloud\s+(?:engineer|architect))\b", "Cloud Engineer"),
        (r"\b(security\s+(?:engineer|analyst))\b", "Security Engineer"),
        (r"\b(qa\s+(?:engineer|analyst)|quality\s+assurance)\b", "QA Engineer"),
        (r"\b(product\s+manager)\b", "Product Manager"),
        (r"\b(project\s+manager)\b", "Project Manager"),
        (r"\b(ux\s+(?:designer|researcher)|ui\s+designer)\b", "UX/UI Designer"),
        (r"\b(system\s+(?:administrator|engineer))\b", "Systems Engineer"),
        (r"\b(database\s+administrator|dba)\b", "Database Administrator"),
        (r"\b(network\s+engineer)\b", "Network Engineer"),
        (r"\b(site\s+reliability\s+engineer|sre)\b", "SRE"),
        (r"\b(technical\s+(?:lead|architect))\b", "Technical Lead"),
        (r"\b(web\s+developer)\b", "Web Developer"),
    ]
    text_lower = text.lower()
    for pattern, role in role_patterns:
        if re.search(pattern, text_lower):
            roles.append(role)
    return roles


def _detect_domains(skills: Dict[str, List[str]], text: str) -> List[str]:
    """Detect domain areas from skills and text content."""
    domains = []
    text_lower = text.lower()

    domain_signals = [
        (["machine learning", "deep learning", "tensorflow", "pytorch", "nlp",
          "computer vision", "data science"], "AI/ML"),
        (["react", "angular", "vue", "svelte", "frontend", "html", "css",
          "javascript", "typescript", "ui/ux"], "Frontend"),
        (["django", "flask", "fastapi", "spring", "express", "backend",
          "api", "microservices"], "Backend"),
        (["docker", "kubernetes", "terraform", "ci/cd", "jenkins",
          "devops", "infrastructure"], "DevOps/Infrastructure"),
        (["aws", "azure", "gcp", "cloud", "serverless", "lambda"], "Cloud"),
        (["postgresql", "mongodb", "redis", "database", "sql",
          "data engineering", "etl"], "Data/Databases"),
        (["ios", "android", "react native", "flutter", "mobile"], "Mobile"),
        (["cybersecurity", "penetration", "soc", "security", "encryption"], "Security"),
        (["figma", "sketch", "ux design", "ui design", "wireframing"], "Design"),
        (["hadoop", "spark", "kafka", "big data", "data pipeline",
          "data analysis"], "Big Data & Analytics"),
    ]

    all_skills_flat = []
    for cat_skills in skills.values():
        all_skills_flat.extend(cat_skills)
    combined = " ".join(all_skills_flat) + " " + text_lower

    for signals, domain in domain_signals:
        matches = sum(1 for s in signals if s in combined)
        if matches >= 2:
            domains.append(domain)

    return domains if domains else ["General Software Engineering"]


# ── Job Database ────────────────────────────────────────────────────────────

# Realistic company templates by size/type
_COMPANIES = {
    "faang": [
        {"name": "TechNova Inc.", "type": "Large Tech", "size": "10,000+", "location": "San Francisco, CA (Remote)"},
        {"name": "CloudScale Systems", "type": "Large Tech", "size": "5,000+", "location": "Seattle, WA (Hybrid)"},
        {"name": "DataStream Corp.", "type": "Large Tech", "size": "8,000+", "location": "Austin, TX (Remote)"},
        {"name": "QuantumByte Labs", "type": "Large Tech", "size": "15,000+", "location": "New York, NY (Hybrid)"},
    ],
    "startup": [
        {"name": "NexGen AI", "type": "AI Startup", "size": "50-200", "location": "San Francisco, CA (Remote)"},
        {"name": "Veloce Labs", "type": "SaaS Startup", "size": "20-100", "location": "Austin, TX (Remote)"},
        {"name": "Arclight Technologies", "type": "FinTech Startup", "size": "100-500", "location": "New York, NY (Hybrid)"},
        {"name": "PulsePoint Health", "type": "HealthTech Startup", "size": "30-150", "location": "Boston, MA (Remote)"},
        {"name": "GreenByte Solutions", "type": "CleanTech Startup", "size": "10-50", "location": "Denver, CO (Remote)"},
    ],
    "mid": [
        {"name": "Meridian Software", "type": "Mid-size Tech", "size": "500-2,000", "location": "Chicago, IL (Hybrid)"},
        {"name": "Apex Digital", "type": "Digital Agency", "size": "200-800", "location": "Los Angeles, CA (Remote)"},
        {"name": "Ironclad Systems", "type": "Enterprise Software", "size": "1,000-5,000", "location": "Raleigh, NC (Hybrid)"},
        {"name": "Prism Analytics", "type": "Data Analytics", "size": "300-1,000", "location": "Seattle, WA (Remote)"},
        {"name": "Vertex Cloud", "type": "Cloud Services", "size": "500-2,000", "location": "Portland, OR (Remote)"},
    ],
    "enterprise": [
        {"name": "Fortis Financial", "type": "Financial Services", "size": "10,000+", "location": "New York, NY (Hybrid)"},
        {"name": "MedVista Health", "type": "Healthcare", "size": "5,000+", "location": "Boston, MA (On-site)"},
        {"name": "TerraLogistics", "type": "Logistics/Supply Chain", "size": "8,000+", "location": "Atlanta, GA (Hybrid)"},
        {"name": "Sentinel Defense", "type": "Defense/Gov Tech", "size": "20,000+", "location": "Washington, DC (On-site)"},
    ],
}

# Job role templates with required skills and domains
_JOB_TEMPLATES = [
    {
        "title": "Software Engineer",
        "variants": ["Software Engineer", "Software Developer", "Application Developer"],
        "core_skills": ["python", "javascript", "sql", "git", "docker"],
        "bonus_skills": ["aws", "kubernetes", "react", "postgresql", "ci/cd"],
        "domains": ["Backend", "Frontend", "General Software Engineering"],
        "levels": ["entry", "mid", "senior"],
        "salary_ranges": {"entry": "$75K-$95K", "mid": "$100K-$140K", "senior": "$140K-$190K"},
        "description": "Design, develop, and maintain software applications. Collaborate with cross-functional teams to deliver high-quality solutions.",
    },
    {
        "title": "Frontend Developer",
        "variants": ["Frontend Engineer", "UI Engineer", "Web Developer"],
        "core_skills": ["javascript", "react", "html", "css", "typescript"],
        "bonus_skills": ["next.js", "vue", "angular", "figma", "sass"],
        "domains": ["Frontend", "Design"],
        "levels": ["entry", "mid", "senior"],
        "salary_ranges": {"entry": "$70K-$90K", "mid": "$95K-$130K", "senior": "$130K-$175K"},
        "description": "Build responsive, performant user interfaces. Translate designs into pixel-perfect implementations with modern frameworks.",
    },
    {
        "title": "Backend Developer",
        "variants": ["Backend Engineer", "API Developer", "Server-Side Engineer"],
        "core_skills": ["python", "sql", "postgresql", "docker", "git"],
        "bonus_skills": ["fastapi", "django", "redis", "kubernetes", "aws"],
        "domains": ["Backend", "Data/Databases"],
        "levels": ["entry", "mid", "senior"],
        "salary_ranges": {"entry": "$75K-$95K", "mid": "$100K-$140K", "senior": "$140K-$185K"},
        "description": "Build and maintain server-side applications, APIs, and microservices. Optimize for performance, scalability, and reliability.",
    },
    {
        "title": "Full Stack Developer",
        "variants": ["Full Stack Engineer", "Full-Stack Developer"],
        "core_skills": ["javascript", "python", "react", "sql", "git"],
        "bonus_skills": ["typescript", "docker", "aws", "postgresql", "node.js"],
        "domains": ["Frontend", "Backend", "General Software Engineering"],
        "levels": ["mid", "senior"],
        "salary_ranges": {"mid": "$105K-$145K", "senior": "$145K-$195K"},
        "description": "Develop both client and server-side applications. Own features end-to-end from database to UI.",
    },
    {
        "title": "DevOps Engineer",
        "variants": ["DevOps Engineer", "Platform Engineer", "Infrastructure Engineer"],
        "core_skills": ["docker", "kubernetes", "linux", "ci/cd", "bash"],
        "bonus_skills": ["terraform", "aws", "jenkins", "prometheus", "ansible"],
        "domains": ["DevOps/Infrastructure", "Cloud"],
        "levels": ["mid", "senior"],
        "salary_ranges": {"mid": "$110K-$150K", "senior": "$150K-$200K"},
        "description": "Design and maintain CI/CD pipelines, container orchestration, and cloud infrastructure. Ensure system reliability and scalability.",
    },
    {
        "title": "Data Scientist",
        "variants": ["Data Scientist", "Applied Scientist", "Research Scientist"],
        "core_skills": ["python", "machine learning", "statistics", "sql", "pandas"],
        "bonus_skills": ["tensorflow", "pytorch", "scikit-learn", "r", "deep learning"],
        "domains": ["AI/ML", "Big Data & Analytics", "Data/Databases"],
        "levels": ["entry", "mid", "senior"],
        "salary_ranges": {"entry": "$80K-$100K", "mid": "$110K-$150K", "senior": "$150K-$210K"},
        "description": "Apply statistical methods and machine learning to solve business problems. Build predictive models and extract insights from data.",
    },
    {
        "title": "Machine Learning Engineer",
        "variants": ["ML Engineer", "AI Engineer", "Deep Learning Engineer"],
        "core_skills": ["python", "machine learning", "tensorflow", "pytorch", "docker"],
        "bonus_skills": ["kubernetes", "deep learning", "nlp", "computer vision", "aws"],
        "domains": ["AI/ML"],
        "levels": ["mid", "senior"],
        "salary_ranges": {"mid": "$120K-$165K", "senior": "$165K-$230K"},
        "description": "Design and deploy production ML systems. Build training pipelines, optimize model performance, and scale inference infrastructure.",
    },
    {
        "title": "Data Engineer",
        "variants": ["Data Engineer", "Analytics Engineer", "Data Platform Engineer"],
        "core_skills": ["python", "sql", "etl", "data pipeline"],
        "bonus_skills": ["spark", "kafka", "airflow", "aws", "postgresql"],
        "domains": ["Data/Databases", "Big Data & Analytics", "Cloud"],
        "levels": ["mid", "senior"],
        "salary_ranges": {"mid": "$105K-$145K", "senior": "$145K-$195K"},
        "description": "Build and maintain data pipelines, warehouses, and ETL processes. Ensure data quality, reliability, and accessibility.",
    },
    {
        "title": "Cloud Engineer",
        "variants": ["Cloud Engineer", "Cloud Architect", "Cloud Solutions Engineer"],
        "core_skills": ["aws", "docker", "linux", "terraform"],
        "bonus_skills": ["kubernetes", "azure", "gcp", "ci/cd", "ansible"],
        "domains": ["Cloud", "DevOps/Infrastructure"],
        "levels": ["mid", "senior"],
        "salary_ranges": {"mid": "$115K-$155K", "senior": "$155K-$210K"},
        "description": "Design and manage cloud infrastructure. Implement scalable, secure, and cost-effective cloud solutions.",
    },
    {
        "title": "Mobile Developer",
        "variants": ["Mobile Engineer", "iOS Developer", "Android Developer"],
        "core_skills": ["mobile development", "git"],
        "bonus_skills": ["react native", "flutter", "swift", "kotlin", "ios", "android"],
        "domains": ["Mobile"],
        "levels": ["entry", "mid", "senior"],
        "salary_ranges": {"entry": "$72K-$92K", "mid": "$100K-$140K", "senior": "$140K-$185K"},
        "description": "Develop native or cross-platform mobile applications. Optimize for performance, UX, and app store guidelines.",
    },
    {
        "title": "Security Engineer",
        "variants": ["Security Engineer", "Application Security Engineer", "Cybersecurity Analyst"],
        "core_skills": ["security", "linux", "python"],
        "bonus_skills": ["penetration testing", "soc", "encryption", "oauth", "docker"],
        "domains": ["Security"],
        "levels": ["mid", "senior"],
        "salary_ranges": {"mid": "$110K-$155K", "senior": "$155K-$215K"},
        "description": "Protect systems and data through security assessments, incident response, and security architecture design.",
    },
    {
        "title": "QA Engineer",
        "variants": ["QA Engineer", "Test Automation Engineer", "SDET"],
        "core_skills": ["python", "git", "sql"],
        "bonus_skills": ["javascript", "docker", "ci/cd", "agile"],
        "domains": ["General Software Engineering"],
        "levels": ["entry", "mid", "senior"],
        "salary_ranges": {"entry": "$60K-$80K", "mid": "$85K-$120K", "senior": "$120K-$160K"},
        "description": "Design and execute test strategies. Build automated test frameworks and ensure software quality through comprehensive testing.",
    },
    {
        "title": "Site Reliability Engineer",
        "variants": ["SRE", "Reliability Engineer", "Production Engineer"],
        "core_skills": ["linux", "python", "docker", "kubernetes"],
        "bonus_skills": ["prometheus", "grafana", "terraform", "aws", "ci/cd"],
        "domains": ["DevOps/Infrastructure", "Cloud"],
        "levels": ["mid", "senior"],
        "salary_ranges": {"mid": "$120K-$160K", "senior": "$160K-$220K"},
        "description": "Ensure system reliability and performance at scale. Build monitoring, alerting, and automation to minimize downtime.",
    },
    {
        "title": "UX/UI Designer",
        "variants": ["UX Designer", "UI Designer", "Product Designer"],
        "core_skills": ["figma", "ui/ux", "wireframing", "prototyping"],
        "bonus_skills": ["sketch", "user research", "design systems", "html", "css"],
        "domains": ["Design", "Frontend"],
        "levels": ["entry", "mid", "senior"],
        "salary_ranges": {"entry": "$65K-$85K", "mid": "$90K-$125K", "senior": "$125K-$170K"},
        "description": "Create intuitive, accessible user experiences. Conduct user research and translate findings into beautiful, functional designs.",
    },
    {
        "title": "Data Analyst",
        "variants": ["Data Analyst", "Business Analyst", "Analytics Specialist"],
        "core_skills": ["sql", "python", "data analysis"],
        "bonus_skills": ["tableau", "power bi", "pandas", "statistics", "r"],
        "domains": ["Big Data & Analytics", "Data/Databases"],
        "levels": ["entry", "mid", "senior"],
        "salary_ranges": {"entry": "$55K-$72K", "mid": "$75K-$105K", "senior": "$105K-$140K"},
        "description": "Analyze datasets to uncover insights and drive business decisions. Build dashboards, reports, and data visualizations.",
    },
    {
        "title": "Technical Lead",
        "variants": ["Tech Lead", "Engineering Lead", "Staff Engineer"],
        "core_skills": ["python", "javascript", "docker", "git", "agile"],
        "bonus_skills": ["kubernetes", "aws", "postgresql", "ci/cd", "mentoring"],
        "domains": ["General Software Engineering", "Backend"],
        "levels": ["senior", "manager"],
        "salary_ranges": {"senior": "$160K-$210K", "manager": "$190K-$260K"},
        "description": "Lead engineering teams technically. Set architectural direction, mentor engineers, and drive technical excellence.",
    },
    # Internship-specific templates
    {
        "title": "Software Engineering Intern",
        "variants": ["Software Engineering Intern", "SWE Intern", "Development Intern"],
        "core_skills": ["python", "git"],
        "bonus_skills": ["javascript", "sql", "docker", "react"],
        "domains": ["General Software Engineering"],
        "levels": ["intern"],
        "salary_ranges": {"intern": "$30-$50/hr"},
        "description": "Work alongside experienced engineers on real projects. Learn industry best practices while contributing to production code.",
    },
    {
        "title": "Data Science Intern",
        "variants": ["Data Science Intern", "ML Intern", "AI Research Intern"],
        "core_skills": ["python", "statistics"],
        "bonus_skills": ["machine learning", "pandas", "sql", "tensorflow"],
        "domains": ["AI/ML", "Big Data & Analytics"],
        "levels": ["intern"],
        "salary_ranges": {"intern": "$32-$55/hr"},
        "description": "Apply data science techniques to real business problems under mentorship. Gain hands-on experience with ML pipelines.",
    },
]


# ── Core Recommendation Logic ──────────────────────────────────────────────

def _calculate_job_match(
    resume_skills_flat: Set[str],
    resume_domains: List[str],
    experience_level: str,
    job_template: dict,
) -> Tuple[float, List[str], List[str]]:
    """Calculate match score between resume profile and a job template.

    Returns (score, matched_skills, missing_skills).
    """
    # Check level compatibility
    if experience_level not in job_template["levels"]:
        # Allow adjacent levels with a penalty
        level_order = ["intern", "entry", "mid", "senior", "manager"]
        try:
            resume_idx = level_order.index(experience_level)
            closest_distance = min(
                abs(resume_idx - level_order.index(lvl))
                for lvl in job_template["levels"]
            )
        except ValueError:
            closest_distance = 3
        if closest_distance > 1:
            return 0.0, [], []
        level_penalty = 0.85  # 15% penalty for adjacent level
    else:
        level_penalty = 1.0

    all_job_skills = set(job_template["core_skills"] + job_template["bonus_skills"])

    # Core skill coverage (weighted higher)
    core_matched = [s for s in job_template["core_skills"] if s in resume_skills_flat]
    core_coverage = len(core_matched) / max(len(job_template["core_skills"]), 1)

    # Bonus skill coverage
    bonus_matched = [s for s in job_template["bonus_skills"] if s in resume_skills_flat]
    bonus_coverage = len(bonus_matched) / max(len(job_template["bonus_skills"]), 1)

    # Domain overlap
    domain_overlap = len(set(resume_domains) & set(job_template["domains"]))
    domain_score = min(domain_overlap / max(len(job_template["domains"]), 1), 1.0)

    # Weighted score: core skills 50%, bonus skills 25%, domain 25%
    raw_score = (0.50 * core_coverage + 0.25 * bonus_coverage + 0.25 * domain_score) * 100
    final_score = round(raw_score * level_penalty, 1)

    matched = sorted(set(core_matched + bonus_matched))
    missing = sorted(all_job_skills - resume_skills_flat)

    return final_score, matched, missing


def extract_resume_profile(resume_text: str) -> Dict:
    """Extract a structured profile from resume text.

    Returns dict with: skills, roles, experience_level, domains, skill_count.
    """
    skills = _extract_skills(resume_text)
    roles = _extract_role_signals(resume_text)
    experience_level = _detect_experience_level(resume_text)
    domains = _detect_domains(skills, resume_text)

    skills_flat = set()
    for cat_skills in skills.values():
        skills_flat.update(cat_skills)

    return {
        "skills": skills,
        "skills_flat": sorted(skills_flat),
        "roles": roles,
        "experience_level": experience_level,
        "domains": domains,
        "skill_count": len(skills_flat),
    }


def generate_recommendations(
    resume_text: str,
    matched_keywords: Optional[List[str]] = None,
    job_keywords: Optional[List[str]] = None,
    min_score: float = 25.0,
    max_results: int = 15,
) -> Dict:
    """Generate job recommendations based on resume analysis.

    Args:
        resume_text: Extracted resume text.
        matched_keywords: Keywords matched from a prior analysis (optional boost).
        job_keywords: Important JD keywords from prior analysis (optional context).
        min_score: Minimum match score to include (0-100).
        max_results: Maximum number of recommendations to return.

    Returns dict with: profile, recommendations (list), total_matched.
    """
    profile = extract_resume_profile(resume_text)
    resume_skills_flat = set(profile["skills_flat"])

    # Add matched_keywords to skill set for broader matching
    if matched_keywords:
        for kw in matched_keywords:
            if kw.lower() in ALL_SKILLS:
                resume_skills_flat.add(kw.lower())

    recommendations = []

    for template in _JOB_TEMPLATES:
        score, matched, missing = _calculate_job_match(
            resume_skills_flat=resume_skills_flat,
            resume_domains=profile["domains"],
            experience_level=profile["experience_level"],
            job_template=template,
        )

        if score < min_score:
            continue

        # Pick experience level (prefer resume's level, fallback to closest)
        level = profile["experience_level"]
        if level not in template["levels"]:
            level = template["levels"][-1]  # highest available

        salary = template["salary_ranges"].get(level, "Competitive")

        # Pick appropriate company type based on level and role
        if level == "intern":
            company_pool = _COMPANIES["startup"] + _COMPANIES["faang"]
        elif level in ("senior", "manager"):
            company_pool = _COMPANIES["faang"] + _COMPANIES["mid"] + _COMPANIES["enterprise"]
        else:
            company_pool = _COMPANIES["startup"] + _COMPANIES["mid"]

        # Assign different companies to avoid repetition
        company_idx = len(recommendations) % len(company_pool)
        company = company_pool[company_idx]

        # Pick the best title variant
        title = template["variants"][0]
        if level == "senior":
            title = f"Senior {title}"
        elif level == "entry":
            title = f"Junior {title}"
        elif level == "manager":
            title = f"Lead {title}"

        recommendations.append({
            "title": title,
            "company": company["name"],
            "company_type": company["type"],
            "company_size": company["size"],
            "location": company["location"],
            "match_score": score,
            "salary_range": salary,
            "matched_skills": matched[:8],
            "missing_skills": missing[:5],
            "description": template["description"],
            "why_good_fit": _generate_fit_reason(score, matched, profile),
        })

    # Sort by match score descending
    recommendations.sort(key=lambda x: x["match_score"], reverse=True)

    # Limit results
    recommendations = recommendations[:max_results]

    return {
        "profile": {
            "detected_skills": profile["skills_flat"][:20],
            "detected_roles": profile["roles"],
            "experience_level": profile["experience_level"],
            "domains": profile["domains"],
            "skill_count": profile["skill_count"],
        },
        "recommendations": recommendations,
        "total_matched": len(recommendations),
    }


def _generate_fit_reason(
    score: float, matched_skills: List[str], profile: Dict
) -> str:
    """Generate a human-readable reason why this job is a good fit."""
    if score >= 80:
        strength = "excellent"
    elif score >= 60:
        strength = "strong"
    elif score >= 40:
        strength = "good"
    else:
        strength = "potential"

    top_skills = matched_skills[:3]
    if top_skills:
        skills_text = ", ".join(top_skills)
        return (
            f"Your {strength} background in {skills_text} aligns well with this role. "
            f"Your experience level ({profile['experience_level']}) matches the position requirements."
        )
    return (
        f"Your domain expertise in {', '.join(profile['domains'][:2])} "
        f"makes this a {strength} match for your career trajectory."
    )
