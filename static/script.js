// Fonctions JavaScript pour l'outil de dimensionnement télécoms

function updateFrequencies() {
  const technology = document.getElementById("technology").value
  const frequencySelect = document.getElementById("frequency")

  // Effacer les options existantes
  frequencySelect.innerHTML = '<option value="">Sélectionnez une fréquence</option>'

  if (!technology) return

  // Récupérer les fréquences pour la technologie sélectionnée
  fetch(`/get_frequencies/${technology}`)
    .then((response) => response.json())
    .then((frequencies) => {
      for (const [band, freq] of Object.entries(frequencies)) {
        const option = document.createElement("option")
        option.value = freq
        option.textContent = `${freq} MHz (${band} MHz)`
        frequencySelect.appendChild(option)
      }
    })
    .catch((error) => {
      console.error("Erreur lors du chargement des fréquences:", error)
    })
}

function validateForm() {
  const requiredFields = [
    "surface_total",
    "technology",
    "frequency",
    "environment",
    "traffic_demand",
    "qos_requirements",
  ]

  let isValid = true
  const errors = []

  requiredFields.forEach((fieldId) => {
    const element = document.getElementById(fieldId)
    const formGroup = element.closest(".form-group")

    if (!element.value) {
      element.classList.add("error")
      element.classList.remove("success")
      isValid = false

      const label = formGroup.querySelector("label").textContent
      errors.push(label.replace(" *", ""))
    } else {
      element.classList.remove("error")
      element.classList.add("success")
    }
  })

  // Validation spécifique pour les valeurs numériques
  const surfaceTotal = document.getElementById("surface_total")
  if (surfaceTotal.value && Number.parseFloat(surfaceTotal.value) <= 0) {
    surfaceTotal.classList.add("error")
    isValid = false
    errors.push("La surface doit être supérieure à 0")
  }

  const trafficDemand = document.getElementById("traffic_demand")
  if (
    trafficDemand.value &&
    (Number.parseFloat(trafficDemand.value) < 1 || Number.parseFloat(trafficDemand.value) > 100)
  ) {
    trafficDemand.classList.add("error")
    isValid = false
    errors.push("La demande de trafic doit être entre 1 et 100%")
  }

  if (!isValid) {
    showAlert("Veuillez corriger les erreurs suivantes:\n• " + errors.join("\n• "), "error")
  }

  return isValid
}

function showAlert(message, type = "info") {
  // Supprimer les alertes existantes
  const existingAlerts = document.querySelectorAll(".alert")
  existingAlerts.forEach((alert) => alert.remove())

  // Créer une nouvelle alerte
  const alert = document.createElement("div")
  alert.className = `alert alert-${type}`
  alert.textContent = message

  // Insérer l'alerte après le header
  const header = document.querySelector(".header")
  header.insertAdjacentElement("afterend", alert)

  // Supprimer l'alerte après 5 secondes
  setTimeout(() => {
    alert.remove()
  }, 5000)
}

// Amélioration de l'expérience utilisateur
function addInputEnhancements() {
  const inputs = document.querySelectorAll("input, select")

  inputs.forEach((input) => {
    // Supprimer les classes d'erreur lors de la saisie
    input.addEventListener("input", function () {
      this.classList.remove("error")
      if (this.value) {
        this.classList.add("success")
      } else {
        this.classList.remove("success")
      }
    })

    // Ajouter des tooltips pour les champs avec des unités
    if (input.type === "number") {
      input.addEventListener("focus", function () {
        const label = this.closest(".form-group").querySelector("label")
        if (label.textContent.includes("(")) {
          const unit = label.textContent.match(/$$([^)]+)$$/)
          if (unit) {
            this.title = `Valeur en ${unit[1]}`
          }
        }
      })
    }
  })
}

// Animation des résultats
function animateResults() {
  const resultItems = document.querySelectorAll(".result-item")

  resultItems.forEach((item, index) => {
    item.style.opacity = "0"
    item.style.transform = "translateY(20px)"

    setTimeout(() => {
      item.style.transition = "all 0.5s ease-out"
      item.style.opacity = "1"
      item.style.transform = "translateY(0)"
    }, index * 100)
  })
}

// Sauvegarde automatique des données du formulaire
function setupAutoSave() {
  const form = document.querySelector("form")
  const inputs = form.querySelectorAll("input, select")

  inputs.forEach((input) => {
    // Charger les données sauvegardées
    const savedValue = localStorage.getItem(`telecom_${input.id}`)
    if (savedValue && !input.value) {
      input.value = savedValue
    }

    // Sauvegarder lors des changements
    input.addEventListener("change", function () {
      localStorage.setItem(`telecom_${this.id}`, this.value)
    })
  })
}

// Initialisation au chargement de la page
document.addEventListener("DOMContentLoaded", () => {
  // Initialiser les fréquences si une technologie est déjà sélectionnée
  const technologySelect = document.getElementById("technology")
  if (technologySelect.value) {
    updateFrequencies()
  }

  // Ajouter les améliorations UX
  addInputEnhancements()
  setupAutoSave()

  // Animer les résultats s'ils sont présents
  if (document.querySelector(".result-item")) {
    animateResults()
  }

  // Ajouter un indicateur de chargement pour les requêtes
  const form = document.querySelector("form")
  form.addEventListener("submit", function () {
    const submitBtn = this.querySelector('button[type="submit"]')
    const originalText = submitBtn.textContent

    submitBtn.textContent = "⏳ Calcul en cours..."
    submitBtn.disabled = true

    // Restaurer le bouton si la validation échoue
    setTimeout(() => {
      if (submitBtn.disabled) {
        submitBtn.textContent = originalText
        submitBtn.disabled = false
      }
    }, 100)
  })
})

// Fonction utilitaire pour formater les nombres
function formatNumber(num, decimals = 2) {
  return Number.parseFloat(num).toLocaleString("fr-FR", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

// Fonction pour exporter les résultats en CSV
function exportResults() {
  const results = document.querySelectorAll(".result-item")
  let csvContent = "Paramètre,Valeur\n"

  results.forEach((item) => {
    const label = item.querySelector(".label").textContent
    const value = item.querySelector(".value").textContent
    csvContent += `"${label}","${value}"\n`
  })

  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" })
  const link = document.createElement("a")
  const url = URL.createObjectURL(blob)

  link.setAttribute("href", url)
  link.setAttribute("download", "resultats_dimensionnement.csv")
  link.style.visibility = "hidden"

  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}