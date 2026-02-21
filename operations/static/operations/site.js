(() => {
    function toastClassByTag(tag) {
        if (tag === "success") return "toast-success";
        if (tag === "error" || tag === "danger") return "toast-error";
        return "toast-info";
    }

    function iconByTag(tag) {
        if (tag === "success") return "bi-check-circle-fill";
        if (tag === "error" || tag === "danger") return "bi-exclamation-triangle-fill";
        return "bi-info-circle-fill";
    }

    function showSuccessOverlay(text) {
        const overlay = document.getElementById("successOverlay");
        const subtitle = document.getElementById("successOverlayText");
        if (!overlay || !subtitle) return;
        subtitle.textContent = text || "Transaction completed successfully";
        overlay.classList.add("show");
        window.setTimeout(() => overlay.classList.remove("show"), 2200);
    }

    function buildToast(message, tag) {
        const wrapper = document.createElement("div");
        wrapper.className = `toast ${toastClassByTag(tag)}`;
        wrapper.role = "alert";
        wrapper.ariaLive = "assertive";
        wrapper.ariaAtomic = "true";
        wrapper.dataset.bsAutohide = "true";
        wrapper.dataset.bsDelay = tag === "success" ? "2400" : "4200";

        wrapper.innerHTML = `
            <div class="toast-header border-0 bg-transparent">
                <i class="bi ${iconByTag(tag)} me-2"></i>
                <strong class="me-auto text-capitalize">${tag || "info"}</strong>
                <small>now</small>
                <button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
            <div class="toast-body pt-0">${message}</div>
        `;
        return wrapper;
    }

    function initMessages() {
        const source = document.getElementById("flashMessages");
        const stack = document.getElementById("toastStack");
        if (!source || !stack || typeof bootstrap === "undefined") return;

        const entries = source.querySelectorAll("[data-message]");
        entries.forEach((entry) => {
            const message = entry.dataset.message || "";
            const tag = entry.dataset.tag || "info";
            if (!message.trim()) return;

            const toastEl = buildToast(message, tag);
            stack.appendChild(toastEl);
            const toast = new bootstrap.Toast(toastEl);
            toast.show();

            if (tag === "success") {
                showSuccessOverlay(message);
            }
        });
    }

    document.addEventListener("DOMContentLoaded", initMessages);
})();
