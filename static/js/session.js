var socket = io();
var globalQuestionSession = {};
var globalQuestions = [];

socket.on('connect', function () {
    console.debug("Socket: Connected");
    socket.emit('join', globalSessionId);
});

socket.on("session_update", function (session_string) {
    console.debug("Socket: Got session update")
    updateGlobalQuestionSession(JSON.parse(session_string));
});

function updateGlobalQuestionSession(questionSession) {
    console.debug(questionSession);
    globalQuestionSession = questionSession;
    if (globalQuestionSession.is_accepting_questions) {
        document.getElementById("session_status").style.display = "none";
        document.getElementById("session_status").textContent = "";
        document.getElementById("new_question_form").style.display = "";
        let closeSessionButton = document.getElementById("close_session_button");
        if (closeSessionButton !== null) {
            document.getElementById("close_session_button").textContent = "🔒 Close Session";
        }
    } else {
        document.getElementById("session_status").style.display = "";
        document.getElementById("session_status").textContent = "This session has been closed for questions.";
        document.getElementById("new_question_form").style.display = "none";
        let closeSessionButton = document.getElementById("close_session_button");
        if (closeSessionButton !== null) {
            document.getElementById("close_session_button").textContent = "🔓 Open Session";
        }
    }
    updateQuestions(globalQuestionSession.questions);
}

socket.on("session_deleted", function () {
    console.debug("Socket: Got session deleted message");
    document.getElementById("session_status").textContent = "This session has been deleted."
});

function updateQuestions(questions) {
    for (let i = 0; i < questions.length; i++) {
        let question = questions[i];
        let existingElement = document.getElementById(`question_${question._id}`);

        if (existingElement == null) {
            // A new question has appeared
            if (question.hidden && !isAdminPage) {
                continue;
            }
            createQuestionDiv(question, i);
        } else {
            if (question.hidden && !isAdminPage) {
                document.getElementById(`question_${question._id}`).remove();
                continue;
            }
            // Update the order
            let order = (question.hidden) ? i : i - 1000;
            document.getElementById(`question_${question._id}`).style.order = order;
            // Update the upvote count
            document.getElementById(`upvote_question_${question._id}`).innerText = `${question.upvotes.length} 👍`;

            if (isAdminPage) {
                // Hide/Unhide the question
                if (question.hidden) {
                    existingElement.classList.add("hidden");
                    document.getElementById(`hide_question_${question._id}`).textContent = "Unhide 🫣";
                    document.getElementById(`hide_question_${question._id}`).onclick = () => {
                        unhideQuestion(question.session_id, question._id);
                    };
                } else {
                    existingElement.classList.remove("hidden");
                    document.getElementById(`hide_question_${question._id}`).textContent = "Hide 🫣";
                    document.getElementById(`hide_question_${question._id}`).onclick = () => {
                        hideQuestion(question.session_id, question._id);
                    };
                }
            }
        }
    }
}

function createQuestionDiv(question, order) {
    // Create a div for a question
    let questionDiv = document.createElement("div");
    questionDiv.id = `question_${question._id}`;
    questionDiv.classList.add("question");
    if (question.hidden) {
        questionDiv.classList.add("hidden");
    }
    let localOrder = (question.hidden) ? order : order - 1000;
    questionDiv.style.order = localOrder;

    let questionText = document.createElement("div");
    questionText.classList.add("question-text");
    questionText.innerText = question.text;
    questionDiv.appendChild(questionText);

    let questionButtonDiv = document.createElement("div");
    questionButtonDiv.classList.add("question_buttons");

    if (isAdminPage) {
        let hideQuestionButton = document.createElement("button");
        hideQuestionButton.id = `hide_question_${question._id}`;
        hideQuestionButton.role = "button";
        hideQuestionButton.classList.add("styled-button", "hide-button");
        if (question.hidden) {
            hideQuestionButton.onclick = () => {
                unhideQuestion(question.session_id, question._id);
            };
        } else {
            hideQuestionButton.onclick = () => {
                hideQuestion(question.session_id, question._id);
            };
        }
        let hideQuestionText = question.hidden ? "Unhide" : "Hide";
        hideQuestionButton.innerText = `${hideQuestionText} 🫣`;
        questionButtonDiv.appendChild(hideQuestionButton);
    }

    let upvoteQuestionButton = document.createElement("button");
    upvoteQuestionButton.id = `upvote_question_${question._id}`;
    upvoteQuestionButton.role = "button";
    upvoteQuestionButton.classList.add("styled-button", "upvote-button");
    upvoteQuestionButton.onclick = () => {
        upvoteQuestion(question.session_id, question._id);
    }
    upvoteQuestionButton.innerText = `${question.upvotes.length} 👍`;
    questionButtonDiv.appendChild(upvoteQuestionButton);

    questionDiv.appendChild(questionButtonDiv);

    document.getElementById("question_list").appendChild(questionDiv);
}

function upvoteQuestion(session_id, question_id) {
    console.debug("Socket: Sending upvote");
    socket.emit("upvote", { "session_id": session_id, "question_id": question_id })
}

function submitQuestion() {
    if (!globalQuestionSession.is_accepting_questions) {
        alert("This session is not currently accepting questions")
        return
    }
    let questionText = document.getElementById("question-text").value;
    if (questionText == "") {
        alert("You need to add text to your question");
        return;
    }
    socket.emit("ask", { "session_id": globalQuestionSession._id, "text": questionText });
    document.getElementById("question-text").value = "";
}
