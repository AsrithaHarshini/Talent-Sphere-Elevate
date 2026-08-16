document.addEventListener("DOMContentLoaded", function () {
    // Sidebar Toggle
    var el = document.getElementById("wrapper");
    var toggleButton = document.getElementById("menu-toggle");

    if (toggleButton) {
        toggleButton.onclick = function () {
            el.classList.toggle("toggled");
        };
    }
    
    // Auto-dismiss alerts after 5 seconds
    setTimeout(function() {
        var alerts = document.querySelectorAll('.alert');
        alerts.forEach(function(alert) {
            var bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 5000);

    // Theme Toggle (Dark & Light Mode)
    const themeToggleBtn = document.getElementById("theme-toggle");
    const themeIcon = document.getElementById("theme-icon");

    if (themeToggleBtn) {
        // Load saved theme
        const savedTheme = localStorage.getItem("theme") || "dark";
        document.documentElement.setAttribute("data-bs-theme", savedTheme);
        updateThemeIcon(savedTheme);

        themeToggleBtn.addEventListener("click", function () {
            const currentTheme = document.documentElement.getAttribute("data-bs-theme");
            const newTheme = currentTheme === "dark" ? "light" : "dark";
            document.documentElement.setAttribute("data-bs-theme", newTheme);
            localStorage.setItem("theme", newTheme);
            updateThemeIcon(newTheme);
        });
    }

    function updateThemeIcon(theme) {
        if (!themeIcon) return;
        if (theme === "dark") {
            themeIcon.className = "fas fa-sun text-warning";
        } else {
            themeIcon.className = "fas fa-moon text-dark";
        }
    }
});
