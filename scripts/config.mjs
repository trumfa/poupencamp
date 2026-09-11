// Identificador del full de càlcul del POUPE.
//
// És un de sol i ho porta tot: les pestanyes de la base de dades (surten de l'extracció, no es
// toquen a mà) i les de contingut (els textos planers, que edites tu). Ha d'estar compartit com a
// «Qualsevol amb l'enllaç · Lector»; si no, el build s'atura amb un 401.
export const FULL = '1wnKBz760A3rK5Afm6JGfZbkPpFtjz5RCU0jziNyyMFo';

// Les pestanyes que llegeix el build, per famílies.
export const PESTANYES = {
  // les que surten de l'extracció del BOPA i del plànol: no es toquen a mà
  bd: ['documents', 'fitxes', 'unitats', 'recintes', 'articles', 'apartats',
       'claus', 'claus_parametres', 'proteccions'],
  // les que escrius tu
  contingut: ['config', 'textos', 'blocs', 'parametres', 'avisos', 'glossari', 'capes'],
};
