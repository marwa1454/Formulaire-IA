const questions = [
  {
    text: "Depuis combien de temps possédez-vous votre smartphone ?",
    options: ["Moins d'un an", "Entre 1 et 3 ans", "Entre 3 et 5 ans", "Plus de 5 ans"],
    name: "question1"
  },
  {
    text: "Vous utilisez votre smartphone pour ?",
    options: ["Le travail exclusivement", "Le loisir exclusivement", "Les 2"],
    name: "question2"
  },
  {
    text: "Parmi ces propositions, laquelle décrit le mieux l'utilisation de votre smartphone ?",
    options: [
      "10% loisirs et 90% professionnel",
      "30% loisirs et 70% professionnel",
      "50% loisirs et 50% professionnel",
      "70% loisirs et 30% professionnel",
      "90% loisirs et 10% professionnel"
    ],
    name: "question3"
  },
  {
    text: "Vous utilisez votre smartphone pour ?",
    options: [
      "Passer et recevoir des appels (locaux, internationaux ou en visio)",
      "Consulter les mails et messages (SMS)",
      "Consulter les réseaux sociaux (professionnels ou personnels)",
      "Jouer à des jeux (en ligne ou téléchargés)",
      "Regarder des vidéos (YouTube, Netflix, Prime Video, ...)",
      "Manipuler des fichiers (images, photos, documents, ...)"
    ],
    name: "question4",
    multiple: true
  },
  {
    text: "Dans une journée, combien de temps consacrez-vous à la consultation de vos messages et réseaux sociaux ?",
    options: ["Moins d'1h", "Entre 1h et 3h", "Entre 3h et 5h", "Plus de 5h"],
    name: "question5"
  },
  {
    text: "Dans une journée, combien de temps consacrez-vous au visionnage de vidéos ou films ?",
    options: ["Moins d'1h", "Entre 1h et 3h", "Entre 3h et 5h", "Plus de 5h"],
    name: "question6"
  },
  {
    text: "Dans une journée, combien de temps consacrez-vous aux jeux ?",
    options: ["Moins d'1h", "Entre 1h et 3h", "Entre 3h et 5h", "Plus de 5h"],
    name: "question7"
  },
  {
    text: "Dans quel secteur d'activité exercez-vous ?",
    options: [
      "Télécommunication (Développement, Réseau, ...)",
      "Agroalimentaire (Agriculture, Pêche, Élevage, ...)",
      "Commerciale (Vente, Accueil, Service, ...)",
      "Santé (Médecine, Infirmerie, Paramédical, Pharmacie, ...)",
      "Protection Civile et Militaire (Secourisme, Défense, Gestion des Risques, ...)",
      "Économie et Finance (Banques, Comptabilité, Assurance, ...)",
      "Éducation (Enseignement pré-scolaire, primaire, secondaire, ...)",
      "Enseignement Supérieur (Universitaire, Recherche, ...)",
      "Industrie et Logistique (Automatisation, Maintenance, Production, ...)",
      "Informatique (Développement logiciel, Cybersécurité, Data Science, ...)",
      "Juridique (Avocats, Notaires, Conseils juridiques, ...)",
      "Tourisme et Hôtellerie (Hôtels, Restaurants, Agences de voyage, ...)",
      "Énergie et Environnement (Énergies renouvelables, Gestion des déchets, ...)",
      "Médias et Communication (Journalisme, Publicité, Relations publiques, ...)",
      "Autre"
    ],
    name: "question8"
  },
  {
    text: "Selon vous, laquelle de ces propositions décrit le mieux la notion d'intelligence artificielle ?",
    options: [
      "Des technologies qui reposent sur l'utilisation d'algorithmes visant à simuler l'intelligence humaine",
      "Des outils pour résoudre des problèmes humains et remplacer l'intelligence humaine",
      "Des robots dotés d'une conscience et capables d'être autonomes"
    ],
    name: "question9",
    correct: "Des technologies qui reposent sur l'utilisation d'algorithmes visant à simuler l'intelligence humaine"
  },
  {
    text: "L'IA fait appel à différentes sciences et connaissances. Laquelle des propositions suivantes vous semble correcte ?",
    options: [
      "L'informatique, l'électronique, les mathématiques, les neurosciences et les sciences cognitives",
      "La physique, la chimie, l'informatique, la biologie et les mathématiques",
      "Les réseaux sociaux, l'informatique, les sciences du numérique, la philosophie, les sciences et techniques des activités physiques"
    ],
    name: "question10",
    correct: "L'informatique, l'électronique, les mathématiques, les neurosciences et les sciences cognitives"
  },
  {
    text: "Au cours de quelle décennie apparaît l'intelligence artificielle ?",
    options: ["1950", "1960", "1990"],
    name: "question11",
    correct: "1950"
  },
  {
    text: "Selon vous, quel pays est le premier investisseur dans le domaine de l'IA ?",
    options: ["La Chine", "La France", "Les États-Unis"],
    name: "question12",
    correct: "Les États-Unis"
  },
  {
    text: "Qu'est-ce que le Big Data ?",
    options: [
      "Des mégadonnées, des données massives",
      "Un logiciel de piratage de données",
      "Une convention internationale pour l'intelligence artificielle"
    ],
    name: "question13",
    correct: "Des mégadonnées, des données massives"
  },
  {
    text: "Quel serait l'un des domaines concernés par le futur droit associé à l'IA ?",
    options: [
      "Le droit de la santé et du sport",
      "La protection de la vie privée et la propriété intellectuelle",
      "La lutte contre le réchauffement climatique"
    ],
    name: "question14",
    correct: "La protection de la vie privée et la propriété intellectuelle"
  }
];

// Afficher le quiz après clic sur "Commencer"
const startButton = document.getElementById('start-quiz');
if (startButton) {
  startButton.addEventListener('click', () => {
    console.log('Quiz started');
    document.getElementById('intro').style.display = 'none';
    document.getElementById('quiz').style.display = 'block';
  });
} else {
  console.error('Start button not found');
}

// Générer les questions 1 à 14
const questionsContainer = document.getElementById('questions');
if (questionsContainer) {
  questions.forEach((question, index) => {
    const questionDiv = document.createElement('div');
    questionDiv.classList.add('form-group');
    const inputType = question.multiple ? 'checkbox' : 'radio';
    let optionsHtml = question.options
      .map((option) => `
        <label>
          <input type="${inputType}" name="${question.name}${question.multiple ? '[]' : ''}" value="${option}" ${inputType === 'radio' ? 'required' : ''}>
          ${option}
        </label>
      `)
      .join('');
    if (question.name === 'question8') {
      optionsHtml += `
        <div id="other-sector-container" style="display: none;">
          <input type="text" id="other-sector" name="other-sector" placeholder="Précisez votre secteur...">
        </div>
      `;
    }
    questionDiv.innerHTML = `
      <label>${index + 1}. ${question.text}</label>
      <div class="options">${optionsHtml}</div>
    `;
    questionsContainer.appendChild(questionDiv);
  });
} else {
  console.error('Questions container not found');
}

// Afficher le champ "Autre" pour la question 8
const question8Inputs = document.querySelectorAll('input[name="question8"]');
if (question8Inputs.length > 0) {
  question8Inputs.forEach(input => {
    input.addEventListener('change', () => {
      const otherContainer = document.getElementById('other-sector-container');
      const otherInput = document.getElementById('other-sector');
      if (input.value === 'Autre' && input.checked) {
        console.log('Other sector selected');
        otherContainer.style.display = 'block';
      } else if (!Array.from(question8Inputs).some(i => i.value === 'Autre' && i.checked)) {
        console.log('Other sector deselected');
        otherContainer.style.display = 'none';
        otherInput.value = '';
      }
    });
  });
} else {
  console.error('Question 8 inputs not found');
}

// Gérer la soumission
const form = document.getElementById('monFormulaire');
if (form) {
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    console.log('Form submitted');
    const formData = new FormData(form);
    const answers = {
      question1: '',
      question2: '',
      question3: '',
      question4: [],
      question5: '',
      question6: '',
      question7: '',
      question8: '',
      question9: '',
      question10: '',
      question11: '',
      question12: '',
      question13: '',
      question14: '',
      question15: null,
      question16: null,
      other_sector: null
    };

    for (let [key, value] of formData.entries()) {
      if (key.endsWith('[]')) {
        key = key.slice(0, -2);
        if (!answers[key]) answers[key] = [];
        answers[key].push(value);
      } else {
        answers[key] = value;
      }
    }

    // Validation côté client
    const mandatoryFields = ['question1', 'question2', 'question3', 'question5', 'question6', 'question7', 'question8', 'question9', 'question10', 'question11', 'question12', 'question13', 'question14'];
    for (const field of mandatoryFields) {
      if (!answers[field] || answers[field].trim() === '') {
        alert(`Veuillez répondre à la question ${field.replace('question', '')} (obligatoire).`);
        return;
      }
    }
    if (!answers['question4'] || answers['question4'].length === 0) {
      alert('Veuillez sélectionner au moins une option pour la question 4 (obligatoire).');
      return;
    }
    if (answers['question8'] === 'Autre' && (!answers['other-sector'] || answers['other-sector'].trim() === '')) {
      alert('Veuillez préciser votre secteur pour la question 8 (obligatoire lorsque "Autre" est sélectionné).');
      return;
    }

    // Remplacer "Autre" par la valeur personnalisée pour la question 8
    if (answers['question8'] === 'Autre' && answers['other-sector']) {
      answers['question8'] = answers['other-sector'];
    }
    answers['other_sector'] = answers['other-sector'] || null;

    console.log('Answers to send:', JSON.stringify(answers, null, 2));

    // Envoyer les données au backend
    try {
      const response = await fetch('http://localhost:8000/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(answers)
      });
      const result = await response.json();
      console.log('Backend response:', result);
      
      if (response.ok) {
        // Masquer le quiz et afficher uniquement le message de fin
        const quizDiv = document.getElementById('quiz');
        const resultsDiv = document.getElementById('results');
        
        if (quizDiv && resultsDiv) {
          quizDiv.style.display = 'none';
          resultsDiv.style.display = 'block';
          
          // Gestion flexible des réponses du backend
          let message, details, thanks;
          
          if (result.success && result.message && result.details && result.thanks) {
            // Nouveau format avec success, message, details, thanks
            message = result.message;
            details = result.details;
            thanks = result.thanks;
          } else if (result.message && typeof result.message === 'string') {
            // Ancien format avec un seul message
            const lines = result.message.split('\n');
            message = lines[0] || "Le questionnaire est désormais terminé";
            details = lines[1] || "Les résultats sont en cours de traitement et vous seront communiqués par projection à l'écran dans un court instant...";
            thanks = lines[2] || "Nous vous remercions pour votre participation et vous souhaitons une agréable journée!";
          } else {
            // Messages par défaut
            message = "Le questionnaire est désormais terminé";
            details = "Les résultats sont en cours de traitement et vous seront communiqués par projection à l'écran dans un court instant...";
            thanks = "Nous vous remercions pour votre participation et vous souhaitons une agréable fin de journée!";
          }
          
          // Afficher uniquement le message de fin simple
          const endMessage = `
            <div class="end-message" style="text-align: center; padding: 40px; font-size: 18px; line-height: 1.8; font-family: Arial, sans-serif;">
              <h2 style="color: #2c3e50; margin-bottom: 30px; font-size: 24px;">${message}</h2>
              <p style="color: #34495e; margin-bottom: 25px; font-size: 16px;">${details}</p>
              <p style="color: #27ae60; font-weight: bold; font-size: 16px;">${thanks}</p>
            </div>
          `;
          
          document.getElementById('results-text').innerHTML = endMessage;
        } else {
          console.error('Quiz or results div not found');
          // Fallback: afficher une alerte avec le message
          alert("Le questionnaire est désormais terminé\n\nLes résultats sont en cours de traitement et vous seront communiqués par projection à l'écran dans un court instant...\n\nNous vous remercions pour votre participation et vous souhaitons une agréable fin de journée!");
        }
      } else {
        console.error('Backend error:', result);
        alert('Erreur lors de l\'envoi des données : ' + (result.detail || result.message || 'Erreur inconnue'));
      }
    } catch (error) {
      console.error('Fetch error:', error);
      alert('Une erreur s\'est produite lors de l\'envoi des données : ' + error.message);
    }
  });
} else {
  console.error('Form not found');
}