// Load and manage identity profile data

document.addEventListener("DOMContentLoaded", () => {
    const root = document.getElementById("identityProfile");
    if (!root) {
        return;
    }
    const id = root.dataset.id;
    const nameInput = document.getElementById("identityName");
    const companyInput = document.getElementById("identityCompany");
    const tagsInput = document.getElementById("identityTags");
    const faceGallery = document.getElementById("faceGallery");
    const visitTimeline = document.getElementById("visitTimeline");
    const cameraList = document.getElementById("cameraList");

    function loadProfile() {
        fetch(`/api/identities/${id}`)
            .then((r) => r.json())
            .then((data) => {
                nameInput.value = data.name || "";
                companyInput.value = data.company || "";
                tagsInput.value = (data.tags || []).join(", ");

                faceGallery.innerHTML = "";
                (data.faces || []).forEach((f) => {
                    const wrap = document.createElement("div");
                    wrap.className = "me-2 mb-2 text-center";
                    const img = document.createElement("img");
                    img.src = f.url;
                    img.className = "img-thumbnail";
                    wrap.appendChild(img);
                    const btnGroup = document.createElement("div");
                    btnGroup.className = "mt-1";
                    const rem = document.createElement("button");
                    rem.className = "btn btn-sm btn-outline-danger me-1";
                    rem.textContent = "Remove";
                    rem.addEventListener("click", () => {
                        fetch(`/api/identities/${id}/faces/${f.id}`, { method: "DELETE" })
                            .then(loadProfile);
                    });
                    const prim = document.createElement("button");
                    prim.className = "btn btn-sm btn-outline-primary";
                    prim.textContent = f.is_primary ? "Primary" : "Set Primary";
                    prim.disabled = f.is_primary;
                    prim.addEventListener("click", () => {
                        fetch(`/api/identities/${id}/faces/${f.id}/primary`, { method: "POST" })
                            .then(loadProfile);
                    });
                    btnGroup.appendChild(rem);
                    btnGroup.appendChild(prim);
                    wrap.appendChild(btnGroup);
                    faceGallery.appendChild(wrap);
                });

                visitTimeline.innerHTML = "";
                (data.visits || []).forEach((v) => {
                    const li = document.createElement("li");
                    li.className = "list-group-item";
                    li.textContent = v;
                    visitTimeline.appendChild(li);
                });

                cameraList.innerHTML = "";
                (data.cameras || []).forEach((c) => {
                    const li = document.createElement("li");
                    li.className = "list-group-item";
                    li.textContent = c;
                    cameraList.appendChild(li);
                });
            });
    }

    document.getElementById("saveIdentity").addEventListener("click", () => {
        const payload = {
            name: nameInput.value,
            company: companyInput.value,
            tags: tagsInput.value
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean),
        };
        fetch(`/api/identities/${id}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        }).then(loadProfile);
    });

    loadProfile();
});
