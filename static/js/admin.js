// Portfolio CMS — Admin JavaScript

document.addEventListener('DOMContentLoaded', () => {
    // Sidebar toggle for mobile
    const toggle = document.getElementById('sidebarToggle');
    const closeBtn = document.getElementById('sidebarClose');
    const sidebar = document.getElementById('sidebar');

    if (toggle && sidebar) {
        toggle.addEventListener('click', () => {
            sidebar.classList.toggle('open');
        });
    }

    if (closeBtn && sidebar) {
        closeBtn.addEventListener('click', () => {
            sidebar.classList.remove('open');
        });
    }
});

// Delete confirmation modal handler
function confirmDelete(actionUrl, message) {
    const modal = document.getElementById('deleteModal');
    const form = document.getElementById('deleteForm');
    const msg = document.getElementById('deleteModalMsg');

    if (modal && form) {
        form.action = actionUrl;
        if (msg && message) {
            msg.textContent = message;
        }
        modal.style.display = 'flex';
    }
}

function closeDeleteModal() {
    const modal = document.getElementById('deleteModal');
    if (modal) modal.style.display = 'none';
}

// Close modals on Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeDeleteModal();
        const skillModal = document.getElementById('skillModal');
        if (skillModal) skillModal.style.display = 'none';
        const eduModal = document.getElementById('eduModal');
        if (eduModal) eduModal.style.display = 'none';
        const expModal = document.getElementById('expModal');
        if (expModal) expModal.style.display = 'none';
        const certModal = document.getElementById('certModal');
        if (certModal) certModal.style.display = 'none';
        const msgModal = document.getElementById('msgModal');
        if (msgModal) msgModal.style.display = 'none';
    }
});
