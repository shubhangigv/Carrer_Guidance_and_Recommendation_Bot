/**
 * Creates the "Career Guidance Survey" Google Form (9 questions, about 3 minutes).
 * How to use: script.google.com -> New project -> paste -> Save -> Run createCareerSurvey
 * Then open "Execution log" to get the edit link and the share link.
 */
function createCareerSurvey() {
  var form = FormApp.create('Career Guidance Survey');
  form.setDescription(
    'We are final-year students building an AI career guidance system. ' +
    'This anonymous survey has 9 short questions and takes about 3 minutes. ' +
    'No name or email is collected. Answers are used only for our college project.\n\n' +
    'Consent: by submitting this form you agree that your anonymous answers may be used ' +
    'for this college project. You can stop at any time before submitting.');
  form.setCollectEmail(false);

  // The same 1-5 scale everywhere, with anchors so every student reads it the same way.
  var scale = ['1', '2', '3', '4', '5'];
  var anchors = '1 = never done it / very weak, 3 = can do it with help, 5 = can do it well on my own.';

  // 1. Background
  form.addMultipleChoiceItem()
    .setTitle('1. Which year are you in?')
    .setChoiceValues(['1st year', '2nd year', '3rd year'])
    .setRequired(true);

  // 2. Background
  form.addListItem()
    .setTitle('2. What is your branch / field of study?')
    .setChoiceValues(['Engineering (B.E. / B.Tech)', 'Computer Applications (BCA)',
                      'Science (B.Sc)', 'Commerce (B.Com)', 'Management (BBA / BMS)',
                      'Arts / Humanities (BA)', 'Medical / Nursing / Pharmacy',
                      'Design / Fine Arts', 'Law', 'Other'])
    .setRequired(true);

  // 3. Career clarity (proves the problem)
  form.addMultipleChoiceItem()
    .setTitle('3. Do you feel you are on the right career path?')
    .setChoiceValues(['Yes, definitely', 'Mostly yes', 'Not sure', 'No'])
    .setRequired(true);

  // 4. Guidance gap (proves the problem)
  form.addMultipleChoiceItem()
    .setTitle('4. Have you used a career counsellor?')
    .setChoiceValues(['Yes, and it helped', "Yes, but it didn't help much",
                      'No, never', "No, it wasn't available to me"])
    .setRequired(true);

  // 5. Interest profile: one row per RIASEC type (R, I, A, S, E, C)
  form.addGridItem()
    .setTitle('5. How much do you enjoy these activities?')
    .setHelpText('1 = not at all, 3 = it is okay, 5 = I enjoy it a lot.')
    .setRows(['Working with machines, tools or building things',
              'Solving problems, research and analysing data',
              'Designing, writing or creating things',
              'Helping, teaching or caring for people',
              'Leading, persuading or starting a business',
              'Organising data and records, following clear procedures'])
    .setColumns(scale)
    .setRequired(true);

  // 6. Skill profile (row names match SKILL_MAP_V2 in ml/recommender_v2.py).
  //    "No experience" = the student has never tried it (engine level 0).
  //    "Can't assess"  = the student does not know (engine shows a score range instead).
  form.addGridItem()
    .setTitle('6. Rate your current ability in these skills')
    .setHelpText(anchors + ' Choose "No experience" if you have never tried it, ' +
                 'or "Can\'t assess" if you are not sure how good you are.')
    .setRows(['Mathematics', 'Programming', 'Problem Solving', 'Research',
              'Communication', 'Writing', 'Leadership', 'Technical/Practical Skills'])
    .setColumns(scale.concat(['No experience', "Can't assess"]))
    .setRequired(true);

  // 7. Subject profile (row names match SUBJECT_MAP_V2 in ml/recommender_v2.py)
  form.addGridItem()
    .setTitle('7. How good are you at these subjects?')
    .setHelpText(anchors + ' Choose "Not studied" if you have not studied the subject.')
    .setRows(['Mathematics', 'Physics/Chemistry', 'Biology', 'Computer Science',
              'Commerce/Economics', 'Languages', 'Social Sciences', 'Arts/Design'])
    .setColumns(scale.concat(['Not studied']))
    .setRequired(true);

  // 8. Aimed career field (used to evaluate the recommender, not as training labels)
  form.addListItem()
    .setTitle('8. Which career field are you aiming for?')
    .setChoiceValues(['IT & Computing', 'Engineering', 'Healthcare & Medicine',
                      'Life & Physical Sciences', 'Business & Finance', 'Management',
                      'Education', 'Law & Public Service', 'Arts, Design & Media',
                      'Social Work & Psychology', 'Agriculture & Environment',
                      'Not sure yet'])
    .setRequired(true);

  // 9. Demand for the system
  form.addMultipleChoiceItem()
    .setTitle('9. Would you use an AI career guidance tool?')
    .setChoiceValues(['Yes', 'Maybe', 'No'])
    .setRequired(true);

  Logger.log('EDIT link (for you): ' + form.getEditUrl());
  Logger.log('SHARE link (send to students): ' + form.getPublishedUrl());
}
