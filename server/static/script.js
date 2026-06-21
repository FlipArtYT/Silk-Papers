function closeAllMenus() {
    document.querySelectorAll('.control_options.active').forEach(menu => {
        menu.classList.remove('active');
    });
}

function setLoading(loading) {
    document.getElementById('loading-overlay').classList.toggle('active', loading);
}

function showError(message) {
    const toast = document.getElementById('error-toast');
    toast.textContent = message;
    toast.classList.add('active');
    setTimeout(() => toast.classList.remove('active'), 5000);
}

let renameNotebookId = null;
let deleteNotebookId = null;

function openDeleteModal(id) {
    deleteNotebookId = id;
    document.getElementById('delete-modal').classList.add('active');
}

function closeDeleteModal() {
    document.getElementById('delete-modal').classList.remove('active');
    deleteNotebookId = null;
}

function openRenameModal(id, currentName, currentDescription) {
    renameNotebookId = id;
    document.getElementById('rename-name').value = currentName;
    document.getElementById('rename-description').value = currentDescription;
    document.getElementById('rename-modal').classList.add('active');
}

function closeRenameModal() {
    document.getElementById('rename-modal').classList.remove('active');
    renameNotebookId = null;
}

async function refreshNotebooks() {
    setLoading(true);
    try {
        const response = await fetch('/api/notebooks/get_list');
        if (!response.ok) throw new Error('Failed to load notebooks');
        const data = await response.json();
        renderNotebooks(data.result);
    } catch (err) {
        showError(err.message);
    } finally {
        setLoading(false);
    }
}

function renderNotebooks(notebooks) {
    const container = document.getElementById('notebooks_view');
    while (container.firstChild) {
        container.removeChild(container.firstChild);
    }
    for (const notebook of notebooks) {
        container.appendChild(createNotebookCard(notebook));
    }
}

function createNotebookCard(notebook) {
    const a = document.createElement('a');
    a.className = 'notebook_container';
    a.id = notebook.id;
    a.href = '/notebooks/' + notebook.id;

    const info = document.createElement('div');
    info.className = 'notebook_info';

    const h2 = document.createElement('h2');
    h2.className = 'notebook_info_text';
    h2.textContent = notebook.name;
    info.appendChild(h2);

    const p = document.createElement('p');
    p.className = 'notebook_info_text';
    p.textContent = notebook.description;
    info.appendChild(p);

    const doclen = document.createElement('p');
    doclen.className = 'notebook_info_text notebook_docs_len';
    doclen.textContent = 'Sources: ' + (notebook.doclen ?? 0);
    info.appendChild(doclen);

    const controls = document.createElement('div');
    controls.className = 'notebook_controls';

    const menuBtn = document.createElement('button');
    menuBtn.className = 'notebook_menu';
    const span = document.createElement('span');
    span.textContent = '\u22EE';
    menuBtn.appendChild(span);

    const options = document.createElement('div');
    options.className = 'control_options';

    const renameBtn = document.createElement('button');
    renameBtn.className = 'control_option';
    renameBtn.dataset.action = 'rename';
    renameBtn.textContent = 'Rename Notebook';
    options.appendChild(renameBtn);

    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'control_option';
    deleteBtn.dataset.action = 'delete';
    deleteBtn.textContent = 'Delete Notebook';
    options.appendChild(deleteBtn);

    controls.appendChild(menuBtn);
    controls.appendChild(options);

    a.appendChild(info);
    a.appendChild(controls);

    return a;
}

document.getElementById('notebooks_view').addEventListener('click', async (event) => {
    const menuButton = event.target.closest('.notebook_menu');
    if (menuButton) {
        event.preventDefault();
        event.stopPropagation();
        const options = menuButton.parentElement.querySelector('.control_options');
        const wasActive = options.classList.contains('active');
        closeAllMenus();
        if (!wasActive) {
            options.classList.add('active');
        }
        return;
    }

    const option = event.target.closest('.control_option');
    if (option) {
        event.preventDefault();
        event.stopPropagation();
        closeAllMenus();

        const container = option.closest('.notebook_container');
        const notebookId = container.id;
        const action = option.dataset.action;

        if (action === 'rename') {
            const nameEl = container.querySelector('h2');
            const descEl = container.querySelector('p');
            openRenameModal(notebookId, nameEl.textContent, descEl.textContent);
        } else if (action === 'delete') {
            openDeleteModal(notebookId);
        }
        return;
    }

    if (!event.target.closest('.control_options')) {
        closeAllMenus();
    }
});

document.getElementById('rename-save').addEventListener('click', async () => {
    const newName = document.getElementById('rename-name').value.trim();
    const newDescription = document.getElementById('rename-description').value.trim();
    if (!newName) return;

    const id = renameNotebookId;
    closeRenameModal();
    setLoading(true);
    try {
        const response = await fetch('/api/notebooks/rename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ notebook_id: id, new_name: newName, new_description: newDescription })
        });
        if (!response.ok) throw new Error('Failed to rename notebook');
        await refreshNotebooks();
    } catch (err) {
        showError(err.message);
        setLoading(false);
    }
});

document.getElementById('rename-cancel').addEventListener('click', closeRenameModal);

document.getElementById('rename-modal').addEventListener('click', (event) => {
    if (event.target === event.currentTarget) closeRenameModal();
});

document.getElementById('delete-confirm').addEventListener('click', async () => {
    const id = deleteNotebookId;
    closeDeleteModal();
    setLoading(true);
    try {
        const response = await fetch('/api/notebooks/delete', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ notebook_id: id })
        });
        if (!response.ok) throw new Error('Failed to delete notebook');
        await refreshNotebooks();
    } catch (err) {
        showError(err.message);
        setLoading(false);
    }
});

document.getElementById('delete-cancel').addEventListener('click', closeDeleteModal);

document.getElementById('delete-modal').addEventListener('click', (event) => {
    if (event.target === event.currentTarget) closeDeleteModal();
});

document.querySelector('.control_btn').addEventListener('click', async () => {
    setLoading(true);
    try {
        const response = await fetch('/api/notebooks/new', { method: 'POST' });
        if (!response.ok) throw new Error('Failed to create notebook');
        await refreshNotebooks();
    } catch (err) {
        showError(err.message);
        setLoading(false);
    }
});
