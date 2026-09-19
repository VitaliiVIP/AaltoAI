import type { Candidate, JobInfo } from "./types";

// Hardcoded demo data — no backend yet.
// Score thresholds: >=80 green, >=50 yellow, <50 red.

export const JOB: JobInfo = {
  title: "Backend Software Engineer",
  requirements: [
    "4+ years professional backend experience",
    "Python in production",
    "Kubernetes / container orchestration",
    "A cloud platform (AWS, Azure or GCP)",
    "Owns a CI/CD pipeline",
    "At least one shipped microservices project",
  ],
};

export const CANDIDATES: Candidate[] = [
  {
    id: "c1",
    name: "Elina Korhonen",
    file: "/assets/cvs/cv1_elina_korhonen.pdf",
    score: 92,
    years: 6,
    matched: ["Python", "Kubernetes", "AWS", "CI/CD", "6 yrs experience"],
    missing: [],
    summary:
      "Strong match across every requirement. Six years of backend experience, hands-on Kubernetes ownership, and a live cloud-cost optimisation project.",
    recourse: [],
    email: {
      kind: "accept",
      subject: "You're moving forward — Backend Software Engineer",
      body:
        "Hi Elina,\n\nThanks for applying for the Backend Software Engineer role. Your experience with Kubernetes and cloud infrastructure is a strong match for what we're looking for. We'd like to move you to the next round — our team will reach out to schedule a technical interview.\n\nBest,\nHiring Team",
    },
  },
  {
    id: "c2",
    name: "Marcus Chen",
    file: "/assets/cvs/cv2_marcus_chen.pdf",
    score: 84,
    years: 5,
    matched: ["Python", "Kubernetes", "Azure", "CI/CD", "5 yrs experience"],
    missing: ["Infrastructure-as-code (Terraform) exposure is light"],
    summary:
      "Comfortable match. Production Kubernetes experience on Azure, with clear ownership of a payments microservice.",
    recourse: [
      { change: "Add one project using Terraform or another IaC tool", impact: "+4 pts" },
    ],
    email: {
      kind: "accept",
      subject: "You're moving forward — Backend Software Engineer",
      body:
        "Hi Marcus,\n\nThanks for applying for the Backend Software Engineer role. Your Kubernetes and cloud experience matches what we need — we'd like to move you forward to a technical interview.\n\nBest,\nHiring Team",
    },
  },
  {
    id: "c3",
    name: "Emma Laakso",
    file: "/assets/cvs/cv3_emma_laakso.pdf",
    score: 88,
    years: 7,
    matched: ["Python", "Kubernetes", "GCP", "Terraform", "CI/CD", "Kafka", "7 yrs experience"],
    missing: [],
    summary:
      "Excellent match. Seven years of experience, full cloud-native stack including Kafka at scale, and mentoring experience.",
    recourse: [],
    email: {
      kind: "accept",
      subject: "You're moving forward — Backend Software Engineer",
      body:
        "Hi Emma,\n\nThanks for applying for the Backend Software Engineer role. Your background across Kubernetes, GCP and event-driven systems is exactly what we're looking for — we'd like to schedule a technical interview.\n\nBest,\nHiring Team",
    },
  },
  {
    id: "c4",
    name: "Aisha Rahman",
    file: "/assets/cvs/cv4_aisha_rahman.pdf",
    score: 76,
    years: 3.5,
    matched: ["Python", "AWS (ECS)", "CI/CD (GitHub Actions)"],
    missing: ["No hands-on Kubernetes", "0.5 years short of the 4-year minimum"],
    summary:
      "Close match. Strong Python and AWS background, but experience is on ECS rather than Kubernetes, and total experience is just under the target.",
    recourse: [
      { change: "Gain hands-on Kubernetes experience (e.g. migrate one ECS service to K8s)", impact: "+9 pts" },
      { change: "Reach the 4-year experience mark", impact: "+4 pts" },
    ],
    email: {
      kind: "reject",
      subject: "Update on your application — Backend Software Engineer",
      body:
        "Hi Aisha,\n\nThank you for applying for the Backend Software Engineer role. Your Python and AWS background is strong, but this role specifically requires hands-on Kubernetes experience, which isn't yet reflected in your profile.\n\nWhat would help: shipping one project that runs on Kubernetes (even migrating an existing ECS service) would directly close this gap. Reaching 4 years of total backend experience would also strengthen your profile.\n\nWe'd welcome a re-application once this experience is in place.\n\nBest,\nHiring Team",
    },
  },
  {
    id: "c5",
    name: "Johan Virtanen",
    file: "/assets/cvs/cv5_johan_virtanen.pdf",
    score: 63,
    years: 4,
    matched: ["Python", "Docker", "4 yrs experience"],
    missing: ["Kubernetes only tried as a proof-of-concept", "No production cloud platform experience"],
    summary:
      "Partial match. Meets the experience bar, but Kubernetes and cloud-platform exposure are both below production level.",
    recourse: [
      { change: "Take a Kubernetes production deployment from proof-of-concept to shipped", impact: "+10 pts" },
      { change: "Get hands-on with one cloud platform (AWS, Azure or GCP) in a real project", impact: "+8 pts" },
    ],
    email: {
      kind: "reject",
      subject: "Update on your application — Backend Software Engineer",
      body:
        "Hi Johan,\n\nThank you for applying for the Backend Software Engineer role. You meet our experience requirement, but this role needs production-level Kubernetes and cloud-platform experience, which your CV shows only at proof-of-concept stage.\n\nWhat would help: shipping your Kubernetes proof-of-concept to production, and gaining hands-on experience with a cloud platform (AWS, Azure or GCP), would directly address this gap.\n\nWe'd welcome a re-application once this experience is in place.\n\nBest,\nHiring Team",
    },
  },
  {
    id: "c6",
    name: "Priya Sharma",
    file: "/assets/cvs/cv6_priya_sharma.pdf",
    score: 55,
    years: 3,
    matched: ["Python", "Flask"],
    missing: ["No Kubernetes", "No cloud platform experience", "1 year short of the 4-year minimum"],
    summary:
      "Below target. Solid Python fundamentals, but no orchestration or cloud experience, and one year short on tenure.",
    recourse: [
      { change: "Learn Kubernetes basics and deploy one containerised service", impact: "+12 pts" },
      { change: "Get hands-on with a cloud platform (AWS, Azure or GCP)", impact: "+8 pts" },
      { change: "Reach 4 years of backend experience", impact: "+5 pts" },
    ],
    email: {
      kind: "reject",
      subject: "Update on your application — Backend Software Engineer",
      body:
        "Hi Priya,\n\nThank you for applying for the Backend Software Engineer role. Your Python fundamentals are solid, but this role requires Kubernetes and cloud-platform experience that isn't yet on your CV.\n\nWhat would help most: deploying one containerised service on Kubernetes, and getting hands-on time with a cloud platform (AWS, Azure or GCP). Reaching 4 years of total experience would also help.\n\nWe'd welcome a re-application once this experience is in place.\n\nBest,\nHiring Team",
    },
  },
  {
    id: "c7",
    name: "Daniel Kwan",
    file: "/assets/cvs/cv7_daniel_kwan.pdf",
    score: 50,
    years: 2.5,
    matched: ["Python", "Basic AWS (Lambda, S3)"],
    missing: ["No Kubernetes", "1.5 years short of the 4-year minimum", "No production-scale project"],
    summary:
      "Borderline. Early-career profile with some cloud exposure via serverless functions, but no orchestration experience or production-scale ownership.",
    recourse: [
      { change: "Learn Kubernetes and ship one containerised service", impact: "+14 pts" },
      { change: "Own one production-scale backend project end-to-end", impact: "+9 pts" },
      { change: "Reach 4 years of backend experience", impact: "+7 pts" },
    ],
    email: {
      kind: "reject",
      subject: "Update on your application — Backend Software Engineer",
      body:
        "Hi Daniel,\n\nThank you for applying for the Backend Software Engineer role. You have a promising start with Python and some AWS exposure, but this role requires more production-scale ownership and Kubernetes experience than your CV currently shows.\n\nWhat would help most: shipping one containerised service on Kubernetes and owning a production-scale project end-to-end. A bit more tenure (4 years total) would also help.\n\nWe'd welcome a re-application once this experience is in place.\n\nBest,\nHiring Team",
    },
  },
  {
    id: "c8",
    name: "Lucas Alves",
    file: "/assets/cvs/cv8_lucas_alves.pdf",
    score: 44,
    years: 3,
    matched: ["3 yrs professional experience"],
    missing: ["No Python backend experience", "No Kubernetes", "No cloud experience", "Background is frontend (React/TypeScript)"],
    summary:
      "Weak match for this role. Strong frontend background, but the role is backend-focused and none of the core requirements are met yet.",
    recourse: [
      { change: "Build and ship one Python backend service in production", impact: "+18 pts" },
      { change: "Learn Kubernetes and deploy that service on it", impact: "+10 pts" },
      { change: "Get hands-on with a cloud platform (AWS, Azure or GCP)", impact: "+7 pts" },
    ],
    email: {
      kind: "reject",
      subject: "Update on your application — Backend Software Engineer",
      body:
        "Hi Lucas,\n\nThank you for applying for the Backend Software Engineer role. Your experience is strongly frontend-focused (React/TypeScript), and this role specifically requires backend ownership in Python — which isn't yet reflected in your CV.\n\nWhat would help most: shipping one Python backend service in production, ideally deployed on Kubernetes. This is a bigger shift than the other gaps we usually flag, so take this as a longer-term note rather than a quick fix.\n\nWe'd welcome a re-application once this experience is in place.\n\nBest,\nHiring Team",
    },
  },
  {
    id: "c9",
    name: "Nora Salminen",
    file: "/assets/cvs/cv9_nora_salminen.pdf",
    score: 33,
    years: 4,
    matched: ["Python (test automation)", "4 yrs professional experience"],
    missing: ["No production backend ownership", "No Kubernetes", "No cloud experience"],
    summary:
      "Weak match. Python experience is limited to test automation rather than production backend development.",
    recourse: [
      { change: "Build and own one production backend service (not test tooling)", impact: "+20 pts" },
      { change: "Learn Kubernetes and deploy it there", impact: "+9 pts" },
      { change: "Get hands-on with a cloud platform (AWS, Azure or GCP)", impact: "+6 pts" },
    ],
    email: {
      kind: "reject",
      subject: "Update on your application — Backend Software Engineer",
      body:
        "Hi Nora,\n\nThank you for applying for the Backend Software Engineer role. Your Python experience so far is in test automation rather than production backend development, which is the core of this role.\n\nWhat would help most: building and owning one production backend service end-to-end, ideally deployed on Kubernetes.\n\nWe'd welcome a re-application once this experience is in place.\n\nBest,\nHiring Team",
    },
  },
  {
    id: "c10",
    name: "Tomás Hidalgo",
    file: "/assets/cvs/cv10_tomas_hidalgo.pdf",
    score: 21,
    years: 0,
    matched: ["Basic Python (self-taught)"],
    missing: ["No professional software engineering experience", "No Kubernetes", "No cloud experience", "No shipped projects"],
    summary:
      "Not a match yet. No professional engineering experience on record — this profile is at the very start of a backend engineering path.",
    recourse: [
      { change: "Get 1-2 years of professional backend development experience", impact: "+25 pts" },
      { change: "Build and deploy at least one real project (not tutorial-based)", impact: "+15 pts" },
      { change: "Learn Kubernetes and a cloud platform", impact: "+10 pts" },
    ],
    email: {
      kind: "reject",
      subject: "Update on your application — Backend Software Engineer",
      body:
        "Hi Tomás,\n\nThank you for applying for the Backend Software Engineer role. This role requires professional backend development experience that isn't yet reflected in your CV.\n\nWhat would help most: gaining 1-2 years of hands-on backend experience and shipping at least one real (non-tutorial) project. This role isn't the right fit today, but the path above would change that.\n\nWe'd welcome a re-application once this experience is in place.\n\nBest,\nHiring Team",
    },
  },
];
