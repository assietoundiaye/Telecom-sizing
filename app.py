import flask
from flask import Flask, render_template, request, send_file, flash, redirect, url_for, jsonify
import matplotlib
matplotlib.use('Agg')  # Set non-interactive backend
import matplotlib.pyplot as plt
from matplotlib.patches import RegularPolygon
import numpy as np
import math
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
import os
import json
from datetime import datetime

app = Flask(__name__)
app.secret_key = "telecom-sizing-tool-secret"

# Ensure static/patterns directory exists
os.makedirs(os.path.join(app.static_folder, 'patterns'), exist_ok=True)

# Configuration des technologies télécoms
TELECOM_TECHNOLOGIES = {
    'GSM': {
        'name': 'GSM (2G)',
        'frequency_bands': {'900': 900, '1800': 1800},
        'channel_spacing': 0.2,  # MHz
        'tx_power_max': 43,  # dBm (BTS)
        'rx_sensitivity': -104,  # dBm
        'noise_figure': 5,  # dB
        'fade_margin': 10,  # dB
        'interference_margin': 3,  # dB
        'body_loss': 3,  # dB
        'cost_per_bts': 50000,  # € (conservé pour les calculs internes, mais non affiché)
        'cost_per_channel': 2000  # € (conservé pour les calculs internes, mais non affiché)
    },
    'UMTS': {
        'name': 'UMTS (3G)',
        'frequency_bands': {'2100': 2100, '900': 900},
        'channel_spacing': 5,  # MHz
        'tx_power_max': 43,  # dBm
        'rx_sensitivity': -117,  # dBm
        'noise_figure': 7,  # dB
        'fade_margin': 12,  # dB
        'interference_margin': 5,  # dB
        'body_loss': 3,  # dB
        'cost_per_bts': 80000,  # € (conservé pour les calculs internes, mais non affiché)
        'cost_per_channel': 5000  # € (conservé pour les calculs internes, mais non affiché)
    },
    'LTE': {
        'name': 'LTE (4G)',
        'frequency_bands': {'800': 800, '1800': 1800, '2600': 2600},
        'channel_spacing': 20,  # MHz
        'tx_power_max': 46,  # dBm
        'rx_sensitivity': -120,  # dBm
        'noise_figure': 6,  # dB
        'fade_margin': 8,  # dB
        'interference_margin': 4,  # dB
        'body_loss': 3,  # dB
        'cost_per_bts': 120000,  # € (conservé pour les calculs internes, mais non affiché)
        'cost_per_channel': 8000  # € (conservé pour les calculs internes, mais non affiché)
    }
}

# Modèles de propagation
def okumura_hata_path_loss(frequency, distance, hb, hm, environment='urban'):
    """
    Calcule les pertes de propagation selon le modèle Okumura-Hata
    frequency: fréquence en MHz
    distance: distance en km
    hb: hauteur antenne BTS en m
    hm: hauteur antenne mobile en m
    environment: 'urban', 'suburban', 'rural'
    """
    # Facteur de correction pour la hauteur de l'antenne mobile
    if frequency >= 150 and frequency <= 1500:
        ahm = (1.1 * math.log10(frequency) - 0.7) * hm - (1.56 * math.log10(frequency) - 0.8)
    else:
        ahm = 3.2 * (math.log10(11.75 * hm))**2 - 4.97
    
    # Perte de propagation de base
    path_loss = 69.55 + 26.16 * math.log10(frequency) - 13.82 * math.log10(hb) - ahm + (44.9 - 6.55 * math.log10(hb)) * math.log10(distance)
    
    # Correction selon l'environnement
    if environment == 'suburban':
        path_loss = path_loss - 2 * (math.log10(frequency/28))**2 - 5.4
    elif environment == 'rural':
        path_loss = path_loss - 4.78 * (math.log10(frequency))**2 + 18.33 * math.log10(frequency) - 40.94
    
    return path_loss

def free_space_path_loss(frequency, distance):
    """Calcule les pertes en espace libre"""
    return 32.45 + 20 * math.log10(frequency) + 20 * math.log10(distance)

def link_budget_calculation(tech_params, frequency, distance, hb=30, hm=1.5, environment='urban'):
    """
    Calcule le bilan de liaison complet
    """
    # Puissances et sensibilités
    tx_power = tech_params['tx_power_max']
    rx_sensitivity = tech_params['rx_sensitivity']
    
    # Pertes de propagation
    if environment == 'free_space':
        path_loss = free_space_path_loss(frequency, distance)
    else:
        path_loss = okumura_hata_path_loss(frequency, distance, hb, hm, environment)
    
    # Marges et pertes supplémentaires
    fade_margin = tech_params['fade_margin']
    interference_margin = tech_params['interference_margin']
    body_loss = tech_params['body_loss']
    
    # Gains d'antennes (typiques)
    tx_antenna_gain = 18  # dBi (antenne sectorielle)
    rx_antenna_gain = 0   # dBi (antenne mobile)
    
    # Bilan de liaison
    received_power = (tx_power + tx_antenna_gain + rx_antenna_gain - 
                     path_loss - fade_margin - interference_margin - body_loss)
    
    # Marge de liaison
    link_margin = received_power - rx_sensitivity
    
    return {
        'tx_power': tx_power,
        'rx_sensitivity': rx_sensitivity,
        'path_loss': path_loss,
        'fade_margin': fade_margin,
        'interference_margin': interference_margin,
        'body_loss': body_loss,
        'tx_antenna_gain': tx_antenna_gain,
        'rx_antenna_gain': rx_antenna_gain,
        'received_power': received_power,
        'link_margin': link_margin,
        'link_feasible': link_margin > 0
    }

def calculate_cell_radius(tech_params, frequency, environment='urban', hb=30, hm=1.5):
    """
    Calcule le rayon de cellule maximum basé sur le bilan de liaison
    """
    # Recherche dichotomique pour trouver le rayon maximum
    min_radius = 0.1  # km
    max_radius = 50   # km
    tolerance = 0.01
    
    while max_radius - min_radius > tolerance:
        test_radius = (min_radius + max_radius) / 2
        link_budget = link_budget_calculation(tech_params, frequency, test_radius, hb, hm, environment)
        
        if link_budget['link_feasible']:
            min_radius = test_radius
        else:
            max_radius = test_radius
    
    return min_radius

def calculate_advanced_dimensioning(surface_total, technology, frequency, environment, 
                                  traffic_demand, qos_requirements, hb=30, hm=1.5):
    """
    Calcule le dimensionnement avancé avec bilan de liaison et QoS
    """
    tech_params = TELECOM_TECHNOLOGIES[technology]
    
    # Calcul du rayon de cellule optimal
    max_radius = calculate_cell_radius(tech_params, frequency, environment, hb, hm)
    
    # Ajustement du rayon selon la charge de trafic et QoS
    traffic_factor = min(1.0, traffic_demand / 100)  # Normalisation du trafic
    qos_factor = qos_requirements / 100  # Facteur de qualité
    
    # Réduction du rayon pour maintenir la QoS avec forte charge
    optimal_radius = max_radius * (1 - 0.3 * traffic_factor) * qos_factor
    
    # Surface de cellule (hexagonale)
    cell_area = (3 * math.sqrt(3) / 2) * optimal_radius**2
    
    # Nombre de cellules nécessaires
    num_cells = math.ceil(surface_total / cell_area)
    
    # Calcul de la capacité selon la technologie
    if technology == 'GSM':
        channels_per_cell = min(8, max(1, int(traffic_demand / 10)))  # TCH/F
        capacity_per_cell = channels_per_cell * 0.9  # Facteur de charge
    elif technology == 'UMTS':
        # Capacité basée sur les codes et l'interférence
        capacity_per_cell = min(64, int(traffic_demand * 1.5))
    else:  # LTE
        # Capacité basée sur les ressources physiques
        capacity_per_cell = min(200, int(traffic_demand * 2))
    
    total_capacity = num_cells * capacity_per_cell
    
    # Calcul des coûts (conservé pour compatibilité, mais non affiché)
    cost_infrastructure = num_cells * tech_params['cost_per_bts']
    cost_equipment = num_cells * channels_per_cell * tech_params['cost_per_channel'] if technology == 'GSM' else num_cells * tech_params['cost_per_channel']
    total_cost = cost_infrastructure + cost_equipment
    
    # Bilan de liaison pour la cellule type
    link_budget = link_budget_calculation(tech_params, frequency, optimal_radius, hb, hm, environment)
    
    # Distance de réutilisation (cluster size optimal selon la technologie)
    if technology == 'GSM':
        cluster_size = 7 if qos_requirements > 80 else 4
    elif technology == 'UMTS':
        cluster_size = 1  # Réutilisation universelle
    else:  # LTE
        cluster_size = 1  # Réutilisation universelle avec coordination d'interférence
    
    reuse_distance = optimal_radius * math.sqrt(3 * cluster_size)
    
    return {
        'technology': tech_params['name'],
        'frequency': frequency,
        'environment': environment,
        'max_radius': max_radius,
        'optimal_radius': optimal_radius,
        'cell_area': cell_area,
        'num_cells': num_cells,
        'cluster_size': cluster_size,
        'reuse_distance': reuse_distance,
        'capacity_per_cell': capacity_per_cell,
        'total_capacity': total_capacity,
        'channels_per_cell': channels_per_cell if technology == 'GSM' else capacity_per_cell,
        'cost_infrastructure': cost_infrastructure,  # Conservé mais non affiché
        'cost_equipment': cost_equipment,  # Conservé mais non affiché
        'total_cost': total_cost,  # Conservé mais non affiché
        'link_budget': link_budget,
        'qos_score': min(100, qos_requirements * (1 - traffic_factor * 0.3))
    }

def draw_advanced_pattern(results, filename="static/patterns/pattern.png"):
    """
    Dessine un motif de réutilisation avancé avec informations détaillées
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 7))
    
    # Graphique 1: Motif de réutilisation
    N = results['cluster_size']
    if N == 1:
        centers = [(0, 0)]
        colors = ['red']
    elif N == 3:
        centers = [(0, 0), (1.5, 0), (0.75, 1.3)]
        colors = ['red', 'blue', 'green']
    elif N == 4:
        centers = [(0, 0), (1.5, 0), (0, 1.3), (1.5, 1.3)]
        colors = ['red', 'blue', 'green', 'yellow']
    elif N == 7:
        centers = [(0, 0), (1.5, 0), (0.75, 1.3), (-0.75, 1.3), (-1.5, 0), (-0.75, -1.3), (0.75, -1.3)]
        colors = ['red', 'blue', 'green', 'yellow', 'purple', 'orange', 'cyan']
    else:
        centers = [(0, 0)]
        colors = ['red']
    
    radius = results['optimal_radius']
    
    for i, center in enumerate(centers):
        hexagon = RegularPolygon(center, numVertices=6, radius=0.8, orientation=0,
                                facecolor=colors[i % len(colors)], alpha=0.6, edgecolor='black', linewidth=2)
        ax1.add_patch(hexagon)
        ax1.text(center[0], center[1], f'C{i+1}', ha='center', va='center', fontweight='bold', fontsize=10)
    
    ax1.set_aspect('equal')
    ax1.set_xlim(-2.5, 2.5)
    ax1.set_ylim(-2.5, 2.5)
    ax1.set_title(f'Motif de Réutilisation - {results["technology"]}\nTaille du cluster: {N}', fontsize=12, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    ax1.set_xlabel('Distance relative')
    ax1.set_ylabel('Distance relative')
    
    # Graphique 2: Bilan de liaison
    link_budget = results['link_budget']
    categories = ['Puiss. TX', 'Gain TX', 'Gain RX', 'Pertes', 'Marges', 'Puiss. RX']
    values = [
        link_budget['tx_power'],
        link_budget['tx_antenna_gain'], 
        link_budget['rx_antenna_gain'],
        -link_budget['path_loss'],
        -(link_budget['fade_margin'] + link_budget['interference_margin'] + link_budget['body_loss']),
        link_budget['received_power']
    ]
    
    colors_bar = ['green', 'blue', 'blue', 'red', 'orange', 'purple']
    bars = ax2.bar(categories, values, color=colors_bar, alpha=0.7)
    
    # Ligne de sensibilité
    ax2.axhline(y=link_budget['rx_sensitivity'], color='red', linestyle='--', linewidth=2, label=f'Sensibilité ({link_budget["rx_sensitivity"]} dBm)')
    
    ax2.set_title('Bilan de Liaison', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Puissance (dBm)')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    plt.xticks(rotation=45)
    
    # Ajout de valeurs sur les barres
    for bar, value in zip(bars, values):
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height + (1 if height > 0 else -3),
                f'{value:.1f}', ha='center', va='bottom' if height > 0 else 'top', fontsize=9)
    
    plt.tight_layout()
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    plt.close()

def generate_advanced_report(params, results, filename="advanced_report.pdf"):
    """
    Génère un rapport PDF professionnel sans les coûts, avec une mise en page améliorée
    """
    # Création du document
    doc = SimpleDocTemplate(filename, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=2.5*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    
    # Styles personnalisés
    title_style = ParagraphStyle(name='TitleStyle', fontName='Helvetica-Bold', fontSize=20, spaceAfter=12, alignment=1)
    subtitle_style = ParagraphStyle(name='SubtitleStyle', fontName='Helvetica', fontSize=12, spaceAfter=12, alignment=1)
    section_style = ParagraphStyle(name='SectionStyle', fontName='Helvetica-Bold', fontSize=14, spaceAfter=10)
    body_style = ParagraphStyle(name='BodyStyle', fontName='Helvetica', fontSize=10, spaceAfter=6, leading=12)
    
    elements = []
    
    # Page de couverture
    elements.append(Paragraph("Rapport de Dimensionnement des Réseaux Télécoms", title_style))
    elements.append(Spacer(1, 1*cm))
    elements.append(Paragraph("Analyse Technique et Bilan de Liaison", subtitle_style))
    elements.append(Spacer(1, 2*cm))
    elements.append(Paragraph(f"Technologie : {results['technology']}", body_style))
    elements.append(Paragraph(f"Environnement : {results['environment'].title()}", body_style))
    elements.append(Paragraph(f"Date : {datetime.now().strftime('%d %B %Y')}", body_style))
    elements.append(Spacer(1, 3*cm))
    elements.append(Paragraph("Réalisé par : [Votre Nom]", body_style))
    elements.append(Paragraph("DIC2 INFO / M1 GLSI / DGI / ESP / UCAD", body_style))
    elements.append(PageBreak())
    
    # Table des matières (simplifiée)
    elements.append(Paragraph("Tableau des Matières", section_style))
    toc = [
        ["1. Paramètres d'Entrée", "2"],
        ["2. Bilan de Liaison", "3"],
        ["3. Résultats de Dimensionnement", "4"],
        ["4. Visualisations", "5"],
    ]
    toc_table = Table(toc, colWidths=[12*cm, 2*cm])
    toc_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), 'Helvetica', 10),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    elements.append(toc_table)
    elements.append(PageBreak())
    
    # Section 1: Paramètres d'entrée
    elements.append(Paragraph("1. Paramètres d'Entrée", section_style))
    param_data = [
        ["Technologie", results['technology']],
        ["Fréquence", f"{results['frequency']} MHz"],
        ["Environnement", results['environment'].title()],
        ["Surface totale", f"{params['surface_total']} km²"],
        ["Demande de trafic", f"{params['traffic_demand']}%"],
        ["Exigences QoS", f"{params['qos_requirements']}%"],
        ["Hauteur antenne BTS", f"{params['hb']} m"],
        ["Hauteur antenne mobile", f"{params['hm']} m"],
    ]
    param_table = Table(param_data, colWidths=[8*cm, 8*cm])
    param_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), 'Helvetica', 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(param_table)
    elements.append(Spacer(1, 1*cm))
    
    # Section 2: Bilan de liaison
    elements.append(Paragraph("2. Bilan de Liaison", section_style))
    link_budget = results['link_budget']
    link_data = [
        ["Puissance d'émission", f"{link_budget['tx_power']} dBm"],
        ["Gain antenne TX", f"{link_budget['tx_antenna_gain']} dBi"],
        ["Gain antenne RX", f"{link_budget['rx_antenna_gain']} dBi"],
        ["Pertes de propagation", f"{link_budget['path_loss']:.1f} dB"],
        ["Marge d'évanouissement", f"{link_budget['fade_margin']} dB"],
        ["Marge d'interférence", f"{link_budget['interference_margin']} dB"],
        ["Pertes corporelles", f"{link_budget['body_loss']} dB"],
        ["Puissance reçue", f"{link_budget['received_power']:.1f} dBm"],
        ["Sensibilité récepteur", f"{link_budget['rx_sensitivity']} dBm"],
        ["Marge de liaison", f"{link_budget['link_margin']:.1f} dB ({'Viable' if link_budget['link_feasible'] else 'Non viable'})"],
    ]
    link_table = Table(link_data, colWidths=[8*cm, 8*cm])
    link_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), 'Helvetica', 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TEXTCOLOR', (1, -1), (1, -1), colors.green if link_budget['link_feasible'] else colors.red),
    ]))
    elements.append(link_table)
    elements.append(Spacer(1, 1*cm))
    
    # Section 3: Résultats de dimensionnement
    elements.append(Paragraph("3. Résultats de Dimensionnement", section_style))
    dim_data = [
        ["Rayon optimal", f"{results['optimal_radius']:.2f} km"],
        ["Rayon maximal", f"{results['max_radius']:.2f} km"],
        ["Surface cellule", f"{results['cell_area']:.2f} km²"],
        ["Nombre de cellules", f"{results['num_cells']}"],
        ["Taille du cluster", f"{results['cluster_size']}"],
        ["Distance de réutilisation", f"{results['reuse_distance']:.2f} km"],
        ["Capacité par cellule", f"{results['capacity_per_cell']:.0f} utilisateurs"],
        ["Capacité totale", f"{results['total_capacity']:.0f} utilisateurs"],
        ["Score QoS prévu", f"{results['qos_score']:.1f}%"],
    ]
    dim_table = Table(dim_data, colWidths=[8*cm, 8*cm])
    dim_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), 'Helvetica', 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(dim_table)
    elements.append(PageBreak())
    
    # Section 4: Visualisations
    elements.append(Paragraph("4. Visualisations", section_style))
    if os.path.exists("static/patterns/pattern.png"):
        img = Image("static/patterns/pattern.png", width=16*cm, height=6*cm)
        img.hAlign = 'CENTER'
        elements.append(img)
        elements.append(Paragraph("Figure 1 : Motif de réutilisation (gauche) et bilan de liaison (droite)", body_style))
    else:
        elements.append(Paragraph("Aucune visualisation disponible.", body_style))
    
    # Fonction pour en-tête et pied de page
    def add_header_footer(canvas, doc):
        canvas.saveState()
        # En-tête
        canvas.setFont("Helvetica-Oblique", 8)
        canvas.drawString(2*cm, A4[1] - 1.5*cm, "Outil de Dimensionnement Télécoms - UCAD 2024-2025")
        canvas.drawRightString(A4[0] - 2*cm, A4[1] - 1.5*cm, datetime.now().strftime("%d/%m/%Y"))
        # Pied de page
        canvas.drawString(2*cm, 1*cm, f"Page {doc.page}")
        canvas.drawRightString(A4[0] - 2*cm, 1*cm, "Réseaux Télécoms et Services")
        canvas.restoreState()
    
    # Génération du PDF
    doc.build(elements, onFirstPage=add_header_footer, onLaterPages=add_header_footer)
    return filename

@app.route('/')
def index():
    return render_template('advanced_index.html', technologies=TELECOM_TECHNOLOGIES)

@app.route('/calculate', methods=['POST'])
def calculate():
    try:
        # Récupération des paramètres
        params = {
            'surface_total': float(request.form['surface_total']),
            'technology': request.form['technology'],
            'frequency': float(request.form['frequency']),
            'environment': request.form['environment'],
            'traffic_demand': float(request.form['traffic_demand']),
            'qos_requirements': float(request.form['qos_requirements']),
            'hb': float(request.form.get('hb', 30)),
            'hm': float(request.form.get('hm', 1.5))
        }
        
        # Validation
        if params['surface_total'] <= 0:
            raise ValueError("La surface totale doit être positive")
        if params['traffic_demand'] < 0 or params['traffic_demand'] > 100:
            raise ValueError("La demande de trafic doit être entre 0 et 100%")
        if params['qos_requirements'] < 0 or params['qos_requirements'] > 100:
            raise ValueError("Les exigences QoS doivent être entre 0 et 100%")
        
        # Calculs
        results = calculate_advanced_dimensioning(
            params['surface_total'],
            params['technology'],
            params['frequency'],
            params['environment'],
            params['traffic_demand'],
            params['qos_requirements'],
            params['hb'],
            params['hm']
        )
        
        # Génération des visualisations et rapport
        draw_advanced_pattern(results)
        generate_advanced_report(params, results)
        
        flash('Calculs effectués avec succès!', 'success')
        return render_template('advanced_index.html', 
                             technologies=TELECOM_TECHNOLOGIES,
                             results=results,
                             params=params,
                             pattern_url=url_for('static', filename='patterns/pattern.png'))
        
    except ValueError as e:
        flash(f'Erreur de validation: {str(e)}', 'error')
        return render_template('advanced_index.html', technologies=TELECOM_TECHNOLOGIES)
    except Exception as e:
        flash(f'Erreur de calcul: {str(e)}', 'error')
        return render_template('advanced_index.html', technologies=TELECOM_TECHNOLOGIES)

@app.route('/get_frequencies/<technology>')
def get_frequencies(technology):
    """API pour récupérer les fréquences disponibles selon la technologie"""
    if technology in TELECOM_TECHNOLOGIES:
        return jsonify(TELECOM_TECHNOLOGIES[technology]['frequency_bands'])
    return jsonify({})

@app.route('/download_report')
def download_report():
    if os.path.exists('advanced_report.pdf'):
        return send_file('advanced_report.pdf', as_attachment=True)
    else:
        flash('Aucun rapport généré. Veuillez effectuer un calcul d\'abord.', 'error')
        return redirect(url_for('index'))

@app.route('/favicon.ico')
def favicon():
    return send_file(os.path.join(app.static_folder, 'favicon.ico'), mimetype='image/x-icon') if os.path.exists(os.path.join(app.static_folder, 'favicon.ico')) else ('', 204)

if __name__ == '__main__':
    app.run(debug=True, port=8000)