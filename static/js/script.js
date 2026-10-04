// ==========================================
// Dynamic Typing Animation Effect
// ==========================================
const words = ["ML Engineer", "Computer Science Student"];
let wordIdx = 0, charIdx = 0, isDeleting = false;

function typeEffect() {
    const target = document.getElementById("typing");
    if (!target) return;

    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        target.textContent = words[0];
        return;
    }

    const currentWord = words[wordIdx];
    if (isDeleting) {
        target.textContent = currentWord.substring(0, charIdx);
        charIdx--;
        if (charIdx < 0) {
            isDeleting = false;
            wordIdx = (wordIdx + 1) % words.length;
            charIdx = 0;
            setTimeout(typeEffect, 400);
            return;
        }
        setTimeout(typeEffect, 40);
    } else {
        target.textContent = currentWord.substring(0, charIdx + 1);
        charIdx++;
        if (charIdx === currentWord.length) {
            isDeleting = true;
            setTimeout(typeEffect, 2200);
            return;
        }
        setTimeout(typeEffect, 80);
    }
}

// ==========================================
// Mobile Menu Navigation Toggle
// ==========================================
function toggleMenu() {
    const mobileMenu = document.getElementById("mobileMenu");
    const hamburger = document.getElementById("hamburgerBtn");
    if (mobileMenu) {
        mobileMenu.classList.toggle("active");
        const isOpen = mobileMenu.classList.contains("active");
        if (hamburger) {
            hamburger.setAttribute("aria-expanded", isOpen);
        }
    }
}

// ==========================================
// Projects View More / View Less Toggle
// ==========================================
function toggleProjects() {
    const grid = document.getElementById("projectsGrid");
    const btn = document.getElementById("viewMoreBtn");
    if (!grid || !btn) return;

    grid.classList.toggle("show-all");
    const isExpanded = grid.classList.contains("show-all");
    btn.setAttribute("aria-expanded", isExpanded);

    if (isExpanded) {
        btn.innerHTML = '<i class="fas fa-folder-minus" aria-hidden="true"></i> Show Less Projects';
        // Trigger reveal check for newly visible cards
        if (typeof revealOnScroll === 'function') {
            revealOnScroll();
        }
    } else {
        btn.innerHTML = '<i class="fas fa-folder-open" aria-hidden="true"></i> View More Projects <i class="fas fa-arrow-right" aria-hidden="true"></i>';
    }
}

// ==========================================
// Scroll Reveal Animations
// ==========================================
function revealOnScroll() {
    const reveals = document.querySelectorAll(".reveal");
    const windowHeight = window.innerHeight;
    const elementVisible = 100;

    reveals.forEach((elem) => {
        const elementTop = elem.getBoundingClientRect().top;
        if (elementTop < windowHeight - elementVisible) {
            elem.classList.add("active");
        }
    });
}

// ==========================================
// Active Navbar Link Scroll Highlight
// ==========================================
function handleNavbarScroll() {
    const sections = document.querySelectorAll("section");
    const navLinks = document.querySelectorAll("#navbar .nav-links li a:not(.btn)");

    let current = "";
    sections.forEach((section) => {
        const sectionTop = section.offsetTop;
        if (window.pageYOffset >= sectionTop - 140) {
            current = section.getAttribute("id");
        }
    });

    navLinks.forEach((a) => {
        a.classList.remove("active");
        if (a.getAttribute("href") === "#" + current) {
            a.classList.add("active");
        }
    });
}

// ==========================================
// Toast Notification Engine
// ==========================================
function showToast(message, isError = false) {
    const toast = document.getElementById("toast");
    if (!toast) return;
    toast.textContent = message;
    toast.style.background = isError ? "rgba(220, 38, 38, 0.95)" : "rgba(16, 185, 129, 0.95)";
    toast.classList.add("show");
    setTimeout(() => { toast.classList.remove("show"); }, 4500);
}

// ==========================================
// Contact Form AJAX Submission with CSRF
// ==========================================
function initContactForm() {
    const form = document.getElementById("contactForm");
    if (!form) return;

    form.addEventListener("submit", async (e) => {
        e.preventDefault();

        const submitBtn = document.getElementById("contactSubmitBtn");
        const btnText = submitBtn ? submitBtn.querySelector(".btn-text") : null;
        const btnLoading = submitBtn ? submitBtn.querySelector(".btn-loading") : null;

        if (submitBtn) submitBtn.disabled = true;
        if (btnText) btnText.style.display = "none";
        if (btnLoading) btnLoading.style.display = "inline-flex";

        const csrfMeta = document.querySelector('meta[name="csrf-token"]');
        const csrfToken = csrfMeta ? csrfMeta.getAttribute("content") : "";

        const formData = new FormData(form);
        if (csrfToken && !formData.get("csrf_token")) {
            formData.append("csrf_token", csrfToken);
        }

        try {
            const res = await fetch("/contact", {
                method: "POST",
                headers: {
                    "X-CSRFToken": csrfToken,
                },
                body: formData,
            });

            const data = await res.json();

            if (res.ok && data.success) {
                // GA4 tracking
                if (typeof gtag === 'function') {
                    gtag('event', 'form_submit', {
                        'event_category': 'Contact',
                        'event_label': 'Portfolio Form'
                    });
                }
                const nameStr = encodeURIComponent(formData.get("name") || "");
                const emailStr = encodeURIComponent(formData.get("email") || "");
                window.location.href = `/thank-you?name=${nameStr}&email=${emailStr}`;
            } else {
                showToast("❌ " + (data.message || "Failed to send message. Please check your inputs."), true);
                if (submitBtn) submitBtn.disabled = false;
                if (btnText) btnText.style.display = "inline-flex";
                if (btnLoading) btnLoading.style.display = "none";
            }
        } catch (err) {
            console.error("Submission error:", err);
            showToast("❌ Network error. Please check your connection and try again.", true);
            if (submitBtn) submitBtn.disabled = false;
            if (btnText) btnText.style.display = "inline-flex";
            if (btnLoading) btnLoading.style.display = "none";
        }
    });
}

// ==========================================
// Canvas Particles Engine
// ==========================================
function initParticleCanvas(canvasId) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !canvas.parentElement) return;

    // Check for reduced motion preference
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        canvas.style.display = "none";
        return;
    }

    // Performance fix: Disable on mobile/tablets (<768px)
    if (window.innerWidth < 768) {
        canvas.style.display = "none";
        return;
    }

    const ctx = canvas.getContext("2d");
    let width = canvas.width = canvas.parentElement.offsetWidth;
    let height = canvas.height = canvas.parentElement.offsetHeight;
    let isVisible = false;
    let animFrameId = null;

    // Only animate when in viewport
    if ('IntersectionObserver' in window) {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    isVisible = true;
                    if (!animFrameId) animate();
                } else {
                    isVisible = false;
                    if (animFrameId) {
                        cancelAnimationFrame(animFrameId);
                        animFrameId = null;
                    }
                }
            });
        }, { threshold: 0.1 });
        observer.observe(canvas.parentElement);
    } else {
        isVisible = true;
    }

    window.addEventListener("resize", () => {
        if (!canvas.parentElement || window.innerWidth < 768) {
            canvas.style.display = "none";
            isVisible = false;
            return;
        }
        canvas.style.display = "block";
        width = canvas.width = canvas.parentElement.offsetWidth;
        height = canvas.height = canvas.parentElement.offsetHeight;
    });

    const particles = [];
    const particleCount = Math.min(Math.floor(width / 35), 30);

    for (let p = 0; p < particleCount; p++) {
        particles.push({
            x: Math.random() * width,
            y: Math.random() * height,
            vx: (Math.random() - 0.5) * 0.4,
            vy: (Math.random() - 0.5) * 0.4,
            radius: Math.random() * 1.5 + 1,
            alpha: Math.random() * 0.35 + 0.15
        });
    }

    function animate() {
        if (!isVisible) return;
        ctx.clearRect(0, 0, width, height);

        for (let i = 0; i < particles.length; i++) {
            let p1 = particles[i];
            p1.x += p1.vx;
            p1.y += p1.vy;

            if (p1.x < 0 || p1.x > width) p1.vx *= -1;
            if (p1.y < 0 || p1.y > height) p1.vy *= -1;

            ctx.beginPath();
            ctx.arc(p1.x, p1.y, p1.radius, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(95, 188, 184, ${p1.alpha})`;
            ctx.fill();

            for (let j = i + 1; j < particles.length; j++) {
                let p2 = particles[j];
                let dx = p1.x - p2.x;
                let dy = p1.y - p2.y;
                let dist = Math.sqrt(dx * dx + dy * dy);

                if (dist < 90) {
                    ctx.beginPath();
                    ctx.moveTo(p1.x, p1.y);
                    ctx.lineTo(p2.x, p2.y);
                    ctx.strokeStyle = `rgba(95, 188, 184, ${0.12 * (1 - dist / 90)})`;
                    ctx.lineWidth = 0.6;
                    ctx.stroke();
                }
            }
        }
        animFrameId = requestAnimationFrame(animate);
    }

    // IntersectionObserver to pause rendering when section is off-screen
    if ("IntersectionObserver" in window) {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    if (!isVisible) {
                        isVisible = true;
                        animFrameId = requestAnimationFrame(animate);
                    }
                } else {
                    isVisible = false;
                    if (animFrameId) {
                        cancelAnimationFrame(animFrameId);
                        animFrameId = null;
                    }
                }
            });
        }, { threshold: 0.1 });

        observer.observe(canvas.parentElement);
    } else {
        animate();
    }
}

// ==========================================
// Accessibility: Close mobile menu on ESC or outside click
// ==========================================
document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
        const mobileMenu = document.getElementById("mobileMenu");
        const hamburger = document.getElementById("hamburgerBtn");
        if (mobileMenu && mobileMenu.classList.contains("active")) {
            mobileMenu.classList.remove("active");
            if (hamburger) hamburger.setAttribute("aria-expanded", "false");
        }
    }
});

// ==========================================
// Initialization
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
    typeEffect();
    revealOnScroll();
    initContactForm();
    initParticleCanvas("particles1");
    initParticleCanvas("particles2");
    initParticleCanvas("particles3");
});

window.addEventListener("scroll", () => {
    revealOnScroll();
    handleNavbarScroll();
});

// ==========================================
// Smooth Scroll with Navbar Offset
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
    const NAVBAR_HEIGHT = document.querySelector("nav#navbar")
        ? document.querySelector("nav#navbar").offsetHeight
        : 75;

    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener("click", function (e) {
            const targetId = this.getAttribute("href");
            if (!targetId || targetId === "#") return;
            const target = document.querySelector(targetId);
            if (!target) return;
            e.preventDefault();
            const top = target.getBoundingClientRect().top + window.pageYOffset - NAVBAR_HEIGHT;
            window.scrollTo({ top, behavior: "smooth" });
        });
    });
});
