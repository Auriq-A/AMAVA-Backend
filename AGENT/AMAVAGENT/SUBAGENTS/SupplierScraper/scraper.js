(function () {
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

            // find parent container (grid or wrapper)
            let parent = container.parentElement;
            while (parent && parent.children.length <= 1) {
                parent = parent.parentElement;
            }

            if (!parent) {
                alert("Couldn't detect product list container.");
                return;
            }

            parent.style.outline = "3px solid blue";

            // collect all product containers
            let products = [];
            Array.from(parent.children).forEach((child, idx) => {
                let html = child.innerHTML.trim();
                if (html.length > 50) { // skip empty divs
                    products.push({
                        index: idx,
                        html: html
                    });
                }
            });

            console.log("✅ Found products:", products.length);
            console.log(JSON.stringify(products));

            alert(`Extracted ${products.length} products. Check console for JSON output.`);

            document.removeEventListener("click", selectContainer, true);
        }, true);
    }

    // Add hover effect to all elements
    document.querySelectorAll("body *").forEach(el => highlightOnHover(el));

    askForProductContainer();
})();
