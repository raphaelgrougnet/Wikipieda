import os

from flask import Flask, render_template, request, abort, redirect, make_response
import re
import bd
from datetime import date, datetime
from babel import numbers, dates
from flask_babel import Babel

app = Flask(__name__)

# Liste des sous-répertoires vers "ajouts"
app.config['MORCEAUX_VERS_AJOUTS'] = ["static", "images", "ajouts"]

# Pour donner static/images/ajouts". Assurez-vous que ce dossier existe !
app.config['ROUTE_VERS_AJOUTS'] = "/".join(app.config['MORCEAUX_VERS_AJOUTS'])

app.config['CHEMIN_VERS_AJOUTS'] = os.path.join(
    app.instance_path.replace("instance", ""),
    *app.config['MORCEAUX_VERS_AJOUTS'])

app.config["BABEL_DEFAULT_LOCALE"] = "fr_CA"
babel = Babel(app)

regexEscape = re.compile(r'<(.*)>.*?|<(.*) />')
regexTitre = re.compile(r'^[a-zA-Z]{1,50}$')
regexAuteur = re.compile(r'^[a-zA-Z0-9\- ]{3,50}$')

dictRegions = {
    "fr_CA": "Francais (Canada)",
    "en_CA": "Anglais (Canada)",
    "en_US": "Anglais (USA)"
}

def lire_cookies():
    """Lit les cookies et retourne un message"""
    return request.cookies.get('auteur')


def obtenirRegionString():
    return dictRegions[app.config['BABEL_DEFAULT_LOCALE']]


def obtenirRegionActuelle():
    return app.config['BABEL_DEFAULT_LOCALE']


@app.route("/")
def index():


    with bd.creer_connexion() as connexion:
        with connexion.get_curseur() as curseur:
            # ATTENTION : s'il y a un million de résultats, vous aurez un million de jeux vidéo en mémoire !!
            curseur.execute('SELECT id,titre FROM terme')
            listeTerme = curseur.fetchall()
            for t in listeTerme:

                if os.path.isfile(os.path.join(app.config['CHEMIN_VERS_AJOUTS'], str(t["id"]))):
                    t["src"] = app.config['ROUTE_VERS_AJOUTS'] + "/" + str(t["id"])
                else:
                    t["src"] = "https://picsum.photos/1920/1080"

    return render_template("principal.jinja2", listeTerme=listeTerme, regionActuelle=obtenirRegionString())


@app.route("/ajouter", methods=["GET", "POST"])
def ajouter():
    titre = request.form.get("titreTerme", default="", type=str)
    contenu = request.form.get("contenuTerme", default="", type=str)
    auteur = request.form.get("auteurTerme", default="", type=str)

    if request.method == "POST":

        if not regexTitre.fullmatch(titre):
            validationTitre = "is-invalid"
        else:
            validationTitre = "is-valid"
        if len(contenu) < 5 or len(contenu) > 2000 or regexEscape.search(contenu):
            validationContenu = "is-invalid"
        else:
            validationContenu = "is-valid"
        if not regexAuteur.fullmatch(auteur):
            validationAuteur = "is-invalid"
        else:
            validationAuteur = "is-valid"

        if validationTitre != "is-valid" or validationContenu != "is-valid" or validationAuteur != "is-valid":
            return render_template("ajouter.jinja2",
                                   validationTitre=validationTitre,
                                   validationContenu=validationContenu,
                                   validationAuteur=validationAuteur,
                                   valTitre=titre,
                                   valContenu=contenu,
                                   valAuteur=auteur,
                                   regionActuelle=obtenirRegionString(),
                                   auteurCookie=lire_cookies())
        else:
            reponse = make_response(
                render_template('ajouter-image.jinja2', valTitre=titre, valContenu=contenu, valAuteur=auteur,
                                regionActuelle=obtenirRegionString()))
            reponse.set_cookie('auteur', auteur)
            return reponse

    return render_template("ajouter.jinja2", regionActuelle=obtenirRegionString(), auteurCookie=lire_cookies())


@app.route("/add", methods=["POST"])
def add():
    titre = request.form.get("titreTerme", default="", type=str)
    contenu = request.form.get("contenuTerme", default="", type=str)
    auteur = request.form.get("auteurTerme", default="", type=str)
    image = request.files["imageTerme"]

    with bd.creer_connexion() as connexion:
        with connexion.get_curseur() as curseur:
            curseur.execute('INSERT INTO terme (titre) VALUES (%(titre)s)', {'titre': titre.lower()})
            lastid = curseur.lastrowid

            curseur.execute(
                'INSERT INTO version (contenu,auteur,date_publication,fk_terme) VALUES (%(contenu)s,%(auteur)s,%(date_publication)s,%(fk_terme)s)',
                {'contenu': contenu, 'auteur': auteur, 'date_publication': datetime.now(), 'fk_terme': lastid})

    if not image:
        src = "/static/images/placeholder.jpg"
    else:
        nom_image = str(lastid)

        chemin_complet = os.path.join(app.config['CHEMIN_VERS_AJOUTS'], nom_image)
        image.save(chemin_complet)

    return redirect("/details?id=" + str(lastid), 303)


@app.route("/details")
def details():
    id = request.args.get("id", default="", type=str)

    if not id:
        abort(400)
    with bd.creer_connexion() as connexion:
        with connexion.get_curseur() as curseur:
            curseur.execute(
                'SELECT t.id,t.titre,v.contenu,v.auteur,v.date_publication as date FROM version as v inner join terme as t on t.id = v.fk_terme WHERE t.id=%(id)s order by date desc limit 1',
                {'id': id})
            details = curseur.fetchone()

    if os.path.isfile(os.path.join(app.config['CHEMIN_VERS_AJOUTS'], str(id))):
        src = app.config['ROUTE_VERS_AJOUTS'] + "/" + str(id)
    else:
        src = "https://picsum.photos/1920/1080"
    date = details["date"]
    datef = dates.format_date(date, locale=obtenirRegionActuelle())

    classe = ""
    if id in request.cookies.get("fav"):
        classe = "-fill"

    return render_template("details.jinja2", details=details, id=id, src=src, regionActuelle=obtenirRegionString(),
                           date=datef, classe=classe)


@app.route("/edit", methods=["POST"])
def edit():
    idT = request.form.get("idTerme", type=int)
    contenu = request.form.get("contenuTerme", default="", type=str)
    auteur = request.form.get("auteurTerme", default="", type=str)
    image = request.files["imageTerme"]
    if image:
        nom_image = str(idT)
        chemin_complet = os.path.join(app.config['CHEMIN_VERS_AJOUTS'], nom_image)
        image.save(chemin_complet)
    with bd.creer_connexion() as connexion:
        with connexion.get_curseur() as curseur:
            curseur.execute(
                'INSERT INTO version (contenu,auteur,date_publication,fk_terme) VALUES (%(contenu)s,%(auteur)s,%(date_publication)s,%(fk_terme)s)',
                {'contenu': contenu, 'auteur': auteur, 'date_publication': datetime.now(), 'fk_terme': idT})

    return redirect("/details?id=" + str(idT), 303)

titreVar = ""

@app.route("/modifier", methods=["POST"])
def modifier():
    global titreVar
    validationTitre = ""
    validationContenu = ""
    validationAuteur = ""

    titre = request.form.get("titreTerme", default="", type=str)
    contenu = request.form.get("contenuTerme", default="", type=str)
    idT = request.form.get("idTerme", default="", type=int)
    auteur = request.form.get("auteurTerme", default="", type=str)



    if not titre:
        titre = titreVar
    else:
        titreVar = titre

    validationTitre = "is-valid"
    if len(contenu) < 5 or len(contenu) > 2000 or regexEscape.search(contenu):
        validationContenu = "is-invalid"
    else:
        validationContenu = "is-valid"

    if not regexAuteur.fullmatch(auteur):
        validationAuteur = "is-invalid"
    else:
        validationAuteur = "is-valid"

    if validationTitre != "is-valid" or validationContenu != "is-valid" or validationAuteur != "is-valid":
        return render_template("modifier.jinja2",
                               validationTitre="",
                               validationContenu=validationContenu,
                               validationAuteur=validationAuteur,
                               valTitre=titreVar,
                               valContenu=contenu,
                               valAuteur=auteur,
                               valId=idT,
                               regionActuelle=obtenirRegionString())

    if os.path.isfile(os.path.join(app.config['CHEMIN_VERS_AJOUTS'], str(idT))):
        src = app.config['ROUTE_VERS_AJOUTS'] + "/" + str(idT)
    else:
        src = "/static/images/placeholder.jpg"
    return render_template("modifier-image.jinja2", valTitre=titreVar, valContenu=contenu, valAuteur=auteur, valId=idT,
                           regionActuelle=obtenirRegionString(), src=src)


@app.route("/fr_CA")
def fr_CA():
    app.config["BABEL_DEFAULT_LOCALE"] = "fr_CA"
    babel = Babel(app)
    return redirect("/", 303)


@app.route("/en_CA")
def en_CA():
    app.config["BABEL_DEFAULT_LOCALE"] = "en_CA"
    babel = Babel(app)
    return redirect("/", 303)


@app.route("/en_US")
def en_US():
    app.config["BABEL_DEFAULT_LOCALE"] = "en_US"
    babel = Babel(app)
    return redirect("/", 303)


@app.route("/old")
def old():

    id = request.args.get("idTerme", default="", type=str)
    if not id:
        abort(400)
    with bd.creer_connexion() as connexion:
        with connexion.get_curseur() as curseur:
            curseur.execute(
                'SELECT t.titre,v.auteur,v.id,v.date_publication as date FROM version as v inner join terme as t on t.id = v.fk_terme WHERE t.id=%(id)s order by date desc',
                {'id': id})
            versions = curseur.fetchall()

            for v in versions:
                date = v["date"]
                datef = dates.format_date(date, locale=obtenirRegionActuelle())
                v["date"] = datef
    return render_template("old.jinja2", versions=versions, regionActuelle=obtenirRegionString())


@app.route("/consulter_ancienne")
def consulter_ancienne():

    vId = request.args.get("idVersion", default="", type=int)
    if not vId:
        abort(400)
    with bd.creer_connexion() as connexion:
        with connexion.get_curseur() as curseur:
            curseur.execute(
                'SELECT t.id,t.titre, v.contenu, v.auteur, v.date_publication from version as v INNER JOIN terme as t ON v.fk_terme = t.id WHERE v.id = %(id)s',
                {
                    'id': vId
                }
            )
            version = curseur.fetchone()
            date = version["date_publication"]
            datef = dates.format_date(date, locale=obtenirRegionActuelle())
            version["date_publication"] = datef
            if os.path.isfile(os.path.join(app.config['CHEMIN_VERS_AJOUTS'], str(version['id']))):
                src = app.config['ROUTE_VERS_AJOUTS'] + "/" + str(version['id'])
            else:
                src = "https://picsum.photos/1920/1080"
    return render_template("consult_old.jinja2", version=version, src=src, regionActuelle=obtenirRegionString())


@app.route("/recherche")
def recherche():

    mot = request.args.get("mot", type=str).strip()
    if not mot:
        return redirect("/", 303)
    with bd.creer_connexion() as connexion:
        with connexion.get_curseur() as curseur:
            curseur.execute(
                'SELECT id,titre FROM terme WHERE titre LIKE %(mot)s',
                {'mot': mot + "%"})
            listeTerme = curseur.fetchall()
    for t in listeTerme:

        if os.path.isfile(os.path.join(app.config['CHEMIN_VERS_AJOUTS'], str(t["id"]))):
            t["src"] = app.config['ROUTE_VERS_AJOUTS'] + "/" + str(t["id"])
        else:
            t["src"] = "https://picsum.photos/1920/1080"
    return render_template("principal.jinja2", listeTerme=listeTerme, mot=mot, regionActuelle=obtenirRegionString())






@app.errorhandler(400)
def page_erreur_400(error):
    return render_template("erreur.jinja2", code_erreur=400, erreur=error, regionActuelle=obtenirRegionString())


@app.errorhandler(404)
def page_erreur_404(error):
    return render_template("erreur.jinja2", code_erreur=404, erreur=error, regionActuelle=obtenirRegionString())


@app.errorhandler(500)
def page_erreur_500(error):
    return render_template("erreur.jinja2", code_erreur=500, erreur=error, regionActuelle=obtenirRegionString())
