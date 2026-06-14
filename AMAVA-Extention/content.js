(function () {
    const SERVER_URL = "http://localhost:8000/upload_products";

    function highlightOnHover(el) {
        el.addEventListener("mouseenter", function () {
            el.__oldOutline = el.style.outline;
            el.style.outline = "2px solid red";
        });
        el.addEventListener("mouseleave", function () {
            el.style.outline = el.__oldOutline || "";
        });
    }

    function askForProductContainer() {
        alert("Hover over the product container and click to select it.");

        document.addEventListener("click", function selectContainer(e) {
            e.preventDefault();
            e.stopPropagation();

            const container = e.target.closest("*");
            if (!container) {
                alert("No container found, try again.");
                return;
            }

            container.style.outline = "3px solid green";
            alert("Product container selected!");

            let parent = container.parentElement;
            while (parent && parent.children.length <= 1) {
                parent = parent.parentElement;
            }

            if (!parent) {
                alert("Couldn't detect product list container.");
                return;
            }

            parent.style.outline = "3px solid blue";

            let products = [];
            Array.from(parent.children).forEach((child, idx) => {
                let html = child.innerHTML.trim();
                if (html.length > 50) {
                    products.push({ index: idx, html: html });
                }
            });

            console.log("✅ Found products:", products.length);
            console.log(JSON.stringify(products));

            fetch(SERVER_URL, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ products, source_url: window.location.href })
            })
                .then(res => res.json())
                .then(data => {
                    console.log("✅ Sent to server:", data);
                    alert(`Extracted ${products.length} products. Sent to backend!`);
                })
                .catch(err => {
                    console.error("❌ Failed to send:", err);
                    alert("Error sending data to server. Check console.");
                });

            document.removeEventListener("click", selectContainer, true);
        }, true);
    }

    // Wait for popup.js trigger
    chrome.runtime.onMessage.addListener((msg) => {
        if (msg.action === "start_scraping") {
            document.querySelectorAll("body *").forEach(el => highlightOnHover(el));
            askForProductContainer();
        }
    });
})();
