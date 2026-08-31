# L'IA ne fonctionne pas : antivirus, proxy et certificats

*Guide d'installation — Cabinet Notarial Zarai*

## Le symptôme

Le Scanner affiche :

> تعذّر التحقّق من شهادة الأمان (SSL) — غالباً بسبب برنامج حماية أو خادم وسيط

ou, en français, une erreur de vérification de certificat.

## La cause

Beaucoup d'antivirus (Kaspersky, ESET, Avast, Bitdefender) et les proxys
d'entreprise inspectent le trafic HTTPS. Pour le faire, ils **re-signent** chaque
connexion avec leur propre autorité de certification. L'application ne reconnaît
pas cette autorité et refuse la connexion — ce qui est le comportement correct :
c'est exactement ainsi qu'elle refuserait une véritable interception.

Ce que le cabinet envoie à l'IA comprend **les scans des cartes d'identité de ses
clients**. La vérification du certificat n'est donc pas une formalité.

## La solution recommandée : installer le certificat de l'antivirus

Cette solution **garde la vérification active**. Elle est à préférer dans tous
les cas.

1. Exporter le certificat racine de l'antivirus au format PEM.
   - Kaspersky : *Paramètres → Réseau → Certificat racine → Exporter*
   - ESET : *Configuration avancée → Web et messagerie → SSL/TLS → Liste des
     certificats connus*
   - Windows : `certmgr.msc` → *Autorités de certification racines de
     confiance* → exporter en **X.509 Base-64 (.CER)**
2. Ouvrir le fichier exporté dans le Bloc-notes. Il commence par
   `-----BEGIN CERTIFICATE-----`.
3. Coller son contenu **à la fin** du fichier :

   ```
   %LOCALAPPDATA%\CabinetNotarialZarai\data\ca_bundle.pem
   ```

   Ne rien supprimer de ce fichier : ajouter à la suite.
4. Redémarrer l'application.

La vérification reste active, et la connexion vers l'IA est acceptée.

## La solution de dernier recours : désactiver la vérification

**À n'utiliser que temporairement, et seulement si l'étape précédente est
impossible.** Tant qu'elle est active, les documents envoyés à l'IA — y compris
les scans de cartes d'identité — partent sur une connexion dont le certificat
n'est pas vérifié.

Elle s'active de deux façons, et **jamais par défaut** :

- créer un fichier `allow_insecure_tls.txt` dans
  `%LOCALAPPDATA%\CabinetNotarialZarai\data\` ; ou
- définir la variable d'environnement `ZARAI_ALLOW_INSECURE_TLS=1`.

Lorsqu'elle est active, **Paramètres → §2 Moteur d'Intelligence Artificielle**
affiche en permanence un bandeau rouge, avec un bouton
*« Réactiver la vérification des certificats »* qui supprime le fichier.

Si l'option a été activée par la variable d'environnement, le bouton le signale :
la variable doit être retirée de la machine, puis l'application redémarrée.

## Vérifier une installation

Sur le poste du client :

```bash
CabinetNotarialZarai.exe --selftest
```

Le rapport confirme que la feuille de style, les deux modèles de reconnaissance
faciale, le dossier de données et la base sont en place. Il est également écrit
dans `%LOCALAPPDATA%\CabinetNotarialZarai\selftest.log`.
