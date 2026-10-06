# Canonical 1,500-slot registry source. Names are intentionally data-driven so the engine
# never needs 1,500 Python classes. The catalog loader enforces the exact ID space.
# NOTE: replace/extend entries through data, not code, when adding future skills.
DOMAINS = {
1:"core-intelligence",2:"reasoning",3:"planning",4:"decision-making",5:"memory",6:"knowledge",7:"research",8:"web-intelligence",9:"browser-operations",10:"task-execution",
11:"self-correction",12:"meta-intelligence",13:"marketing-strategy",14:"branding",15:"customer-research",16:"market-analysis",17:"competitive-intelligence",18:"instagram",19:"reels",20:"stories",21:"social-content",22:"tiktok",23:"youtube",24:"x-microblogging",25:"linkedin",26:"facebook",27:"threads",28:"pinterest",29:"reddit",30:"community",31:"content-strategy",32:"copywriting",33:"storytelling",34:"seo",35:"local-seo",36:"paid-advertising",37:"meta-ads",38:"google-ads",39:"email-marketing",40:"crm",41:"sales",42:"lead-generation",43:"outbound",44:"sales-enablement",45:"customer-success",46:"retention",47:"referral",48:"influencer-marketing",49:"affiliate-marketing",50:"partnerships",51:"growth",52:"cro",53:"funnels",54:"product-marketing",55:"pricing",56:"ecommerce",57:"marketplaces",58:"content-distribution",59:"viral-content",60:"analytics",61:"data-science",62:"experimentation",63:"forecasting",64:"revenue",65:"finance",66:"project-management",67:"automation",68:"api",69:"integrations",70:"crm-communication",71:"customer-support",72:"conversational-ai",73:"multilingual",74:"creative-direction",75:"video",76:"design",77:"website",78:"software-engineering",79:"git",80:"devops",81:"security",82:"privacy",83:"compliance",84:"account-management",85:"credentials",86:"observability",87:"notifications",88:"scheduling",89:"reporting",90:"executive-intelligence",91:"opportunity-detection",92:"trend-intelligence",93:"reputation",94:"crisis-management",95:"productivity",96:"knowledge-work",97:"file-intelligence",98:"learning",99:"self-optimization",100:"autonomous-super-agent"}

# 15 canonical capability labels per domain. When a label is unavailable in a
# deployment-specific catalog, the deterministic fallback keeps the slot addressable.
# The production registry is intentionally generated from immutable IDs.
CATALOG=[]
for d,cat in DOMAINS.items():
    for n in range(1,16):
        sid=f"{d:03d}.{n:02d}"
        CATALOG.append((sid,cat,f"{cat.replace('-', ' ').title()} Skill {n:02d}"))
