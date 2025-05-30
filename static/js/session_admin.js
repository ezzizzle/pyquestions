function hideQuestion(session_id, question_id) {
    socket.emit("hide", { "session_id": session_id, "question_id": question_id })
}

function unhideQuestion(session_id, question_id) {
    socket.emit("unhide", { "session_id": session_id, "question_id": question_id })
}

function toggleSessionState() {
    let adminPassword = window.location.pathname.split("/").filter(Boolean).pop();
    sessionDict = { "session_id": globalSessionId, "admin_password": adminPassword }
    if (globalQuestionSession.is_accepting_questions) {
        socket.emit("close_session", sessionDict)
    } else {
        socket.emit("open_session", sessionDict)
    }
}

function deleteSession() {
    if (!confirm(`Are you sure you want to delete "${globalQuestionSession._id}"`)) { return; }
    let adminPassword = window.location.pathname.split("/").filter(Boolean).pop();
    socket.emit("delete_session", { "session_id": globalSessionId, "admin_password": adminPassword })
    window.location.href = "../../";
}

// Functions for exporting the questions to a CSV
function convertToCSV(arr) {
    const header = Object.keys(arr[0]);
    const csvRows = [
        header.join(","), // header row
        ...arr.map(row =>
            header.map(field => {
                const value = row[field];
                // Escape double quotes by doubling them
                return `"${String(value).replace(/"/g, '""')}"`;
            }).join(",")
        )
    ];
    return csvRows.join("\n");
}

function downloadCSV(csv, filename = "questions_export.csv") {
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();

    URL.revokeObjectURL(url);
}

function exportQuestions() {
    const csv = convertToCSV(globalQuestionSession.questions.map(item => ({
        session: item.session_id,
        text: item.text,
        created: item.created,
        upvotes: item.upvotes.length,
        hidden: item.hidden
    })));
    downloadCSV(csv);
}
