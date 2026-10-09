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
    'No name or email is collected. Answers are used only for our college project.');
  form.setCollectEmail(false);

  var scale = ['1 (Low)', '2', '3', '4', '5 (High)'];

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
    .setTitle('4. Have you ever taken help from a career counsellor?')
    .setChoiceValues(['Yes, and it helped', "Yes, but it didn't help much",
                      'No, never', "No, it wasn't available to me"])
    .setRequired(true);

  // 5. Interest profile: one row per RIASEC type (R, I, A, S, E, C)
  form.addGridItem()
    .setTitle('5. How much do you enjoy these activities?')
    .setRows(['Working with machines, tools or building things',
              'Solving problems, research and analysing data',
              'Designing, writing or creating things',
              'Helping, teaching or caring for people',
              'Leading, persuading or starting a business',
              'Organising data and records, following clear procedures'])
    .setColumns(scale)
    .setRequired(true);

  // 6. Skill profile (names match the recommender's SKILL_MAP)
  form.addGridItem()
    .setTitle('6. Rate your current ability in these skills (1 = beginner, 5 = very advanced)')
    .setRows(['Mathematics', 'Programming', 'Problem Solving', 'Research',
              'Communication', 'Writing', 'Leadership', 'Technical/Practical Skills'])
    .setColumns(scale)
    .setRequired(true);

  // 7. Subject profile
  form.addGridItem()
    .setTitle('7. How much do you enjoy and do well in these subjects?')
    .setRows(['Mathematics', 'Physics/Chemistry', 'Biology', 'Computer Science',
              'Commerce/Economics', 'Languages', 'Social Sciences', 'Arts/Design'])
    .setColumns(scale)
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
    .setTitle('9. Would you use a free AI tool that suggests careers and explains why they suit you?')
    .setChoiceValues(['Yes', 'Maybe', 'No'])
    .setRequired(true);

  Logger.log('EDIT link (for you): ' + form.getEditUrl());
  Logger.log('SHARE link (send to students): ' + form.getPublishedUrl());
}
