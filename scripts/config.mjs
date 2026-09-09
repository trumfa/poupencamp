// Identificador del full de càlcul del POUPE.
//
// És un de sol i ho porta tot: les pestanyes de la base de dades (surten de l'extracció, no es
// toquen a mà) i les de contingut (els textos planers, que edites tu). Ha d'estar compartit com a
// «Qualsevol amb l'enllaç · Lector»; si no, el build s'atura amb un 401.
export const FULL = ''1yjOw63B5teoSN-b0-z91umtKjY9qYoeXytZuhqp34uo'';

// Les pestanyes que llegeix el build, per famílies.
export const PESTANYES = {
  bd: ['Fitxes', 'Parametres', 'UA', 'Normativa', 'Claus', 'Glossari',
       'Claus_parametres', 'Claus_subdivisions', 'Proteccions', 'Planols'],
  contingut: ['config', 'textos_web', 'blocs', 'parametres_public', 'claus_public',
              'valors_public', 'ua_public', 'glossari_public', 'avisos'],
};
