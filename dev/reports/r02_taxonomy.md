# R02 failure taxonomy (run `v1`)

Inspected: 49 failures (discovery + validation). Holdout failures not inspected: 28.

| label | tasks | FP | NM |
|---|---|---|---|
| literal_value | 17 | 12 | 5 |
| extra_join | 15 | 11 | 4 |
| aggregate | 10 | 7 | 3 |
| extra_filter | 10 | 5 | 5 |
| missing_table | 9 | 5 | 4 |
| distinct | 9 | 5 | 4 |
| projection_arity | 9 | 4 | 5 |
| count_distinct | 9 | 7 | 2 |
| group_key | 6 | 5 | 1 |
| other_semantic | 5 | 4 | 1 |
| like_vs_eq | 4 | 2 | 2 |
| set_except | 4 | 1 | 3 |
| literal_case_space | 3 | 3 | 0 |
| set_union | 3 | 1 | 2 |
| order | 3 | 2 | 1 |
| grouping | 3 | 2 | 1 |
| missing_filter | 2 | 2 | 0 |
| set_intersect | 2 | 2 | 0 |
| unparsed | 1 | 0 | 1 |
| limit_vs_max | 1 | 1 | 0 |

## Per task

- **FP** `csu_1` [1row] aggregate  pool_correct=False hint_correct=False
  - Q: In what year was the most degrees conferred?
  - FINAL: `SELECT "degrees"."Year" FROM "degrees" GROUP BY "degrees"."Year" ORDER BY COUNT(*) DESC LIMIT 1`
  - GOLD: `SELECT YEAR FROM degrees GROUP BY YEAR ORDER BY sum(degrees) DESC LIMIT 1`
- **FP** `solvency_ii` [empty] count_distinct, group_key  pool_correct=False hint_correct=False
  - Q: Show the names of products that are in at least two events in ascending alphabetical order of product name.
  - FINAL: `SELECT p.Product_Name FROM Products p JOIN Products_in_Events pie ON p.Product_ID = pie.Product_ID GROUP BY p.Product_ID HAVING COUNT(DISTINCT pie.Event_ID) >= 2 ORDER BY p.Product_Name ASC;`
  - GOLD: `SELECT T1.Product_Name FROM Products AS T1 JOIN Products_in_Events AS T2 ON T1.Product_ID = T2.Product_ID GROUP BY T1.Product_Name HAVING COUNT(*) >= 2 ORDER BY T1.Product_Name`
- **FP** `train_station` [1row] count_distinct, group_key  pool_correct=False hint_correct=False
  - Q: Show the station name with greatest number of trains.
  - FINAL: `SELECT station.Name FROM station JOIN train_station ON station.Station_ID = train_station.Station_ID GROUP BY station.Name ORDER BY COUNT(DISTINCT train_station.Train_ID) DESC LIMIT 1;`
  - GOLD: `SELECT T2.name FROM train_station AS T1 JOIN station AS T2 ON T1.station_id = T2.station_id GROUP BY T1.station_id ORDER BY count(*) DESC LIMIT 1`
- **FP** `soccer_2` [1row] count_distinct, literal_case_space, extra_filter, set_except  pool_correct=False hint_correct=False
  - Q: How many states that have some college students playing in the mid position but not in the goalie position.
  - FINAL: `SELECT COUNT(DISTINCT College.state) AS state_count FROM College JOIN Tryout ON College.cName = Tryout.cName WHERE Tryout.pPos = 'Mid' AND College.cName NOT IN ( SELECT DISTINCT cName FROM Tryout WHERE pPos = 'Goalie' );`
  - GOLD: `SELECT COUNT(*) FROM (SELECT T1.state FROM college AS T1 JOIN tryout AS T2 ON T1.cName = T2.cName WHERE T2.pPos = 'mid' EXCEPT SELECT T1.state FROM college AS T1 JOIN tryout AS T2 ON T1.cName = T2.cName WHERE T2.pPos = 'goalie')`
- **FP** `college_1` [1row] count_distinct, literal_value  pool_correct=False hint_correct=False
  - Q: How many professors attained either Ph.D. or Masters degrees?
  - FINAL: `SELECT COUNT(DISTINCT PROFESSOR.EMP_NUM) AS COUNT FROM PROFESSOR WHERE PROFESSOR.PROF_HIGH_DEGREE IN ('Ph.D.', 'Masters');`
  - GOLD: `SELECT count(*) FROM professor WHERE prof_high_degree = 'Ph.D.' OR prof_high_degree = 'MA'`
- **FP** `journal_committee` [1row] distinct  pool_correct=True hint_correct=False
  - Q: Show the names of editors that are on the committee of journals with sales bigger than 3000.
  - FINAL: `SELECT DISTINCT editor.Name FROM editor JOIN journal_committee ON editor.Editor_ID = journal_committee.Editor_ID JOIN journal ON journal_committee.Journal_ID = journal.Journal_ID WHERE journal.Sales > 3000;`
  - GOLD: `SELECT T2.Name FROM journal_committee AS T1 JOIN editor AS T2 ON T1.Editor_ID = T2.Editor_ID JOIN journal AS T3 ON T1.Journal_ID = T3.Journal_ID WHERE T3.Sales > 3000`
- **FP** `roller_coaster` [empty] distinct, count_distinct, grouping, set_intersect, projection_arity, aggregate  pool_correct=False hint_correct=False
  - Q: What are the country names, area and population which has both roller coasters with speed higher
  - FINAL: `SELECT country.Name, country.Area, country.Population FROM country JOIN roller_coaster ON country.Country_ID = roller_coaster.Country_ID GROUP BY country.Country_ID HAVING COUNT(DISTINCT CASE WHEN CAST(roller_coaster.Speed AS REAL) > 0 THEN roller_coaster.Roller_Coaster_ID END) >= 2;`
  - GOLD: `SELECT T1.name , T1.area , T1.population FROM country AS T1 JOIN roller_coaster AS T2 ON T1.Country_ID = T2.Country_ID WHERE T2.speed > 60 INTERSECT SELECT T1.name , T1.area , T1.population FROM country AS T1 JOIN roller_coaster AS T2 ON T1.Country_ID = T2.Country_ID WHERE T2.speed < 55`
- **FP** `architecture` [multi] distinct, extra_filter, projection_arity  pool_correct=False hint_correct=False
  - Q: What are the ids, names and genders of the architects who built two bridges or one mill?
  - FINAL: `SELECT a.id, a.name, a.gender FROM architect a WHERE a.id IN ( SELECT architect_id FROM bridge GROUP BY architect_id HAVING COUNT(*) >= 2 UNION SELECT architect_id FROM mill GROUP BY architect_id HAVING COUNT(*) >= 1 );`
  - GOLD: `SELECT T1.id , T1.name , T1.gender FROM architect AS T1 JOIN bridge AS T2 ON T1.id = T2.architect_id GROUP BY T1.id HAVING count(*) = 2 UNION SELECT T1.id , T1.name , T1.gender FROM architect AS T1 JOIN mill AS T2 ON T1.id = T2.architect_id GROUP BY T1.id HAVING count(*) = 1`
- **FP** `customer_complaints` [1row] distinct, limit_vs_max, aggregate  pool_correct=False hint_correct=False
  - Q: Return the names of products that have had complaints filed by the customer who has filed the fewest complaints.
  - FINAL: `SELECT Products.product_name FROM Complaints JOIN Products ON Complaints.product_id = Products.product_id JOIN Customers ON Complaints.customer_id = Customers.customer_id GROUP BY Customers.customer_id HAVING COUNT(*) = ( SELECT COUNT(*) FROM Complaints AS C2 GROUP BY C2.customer_id ORDER BY COUNT(*) ASC LIMIT 1 ) ORDER BY Products.product_name;`
  - GOLD: `SELECT DISTINCT t1.product_name FROM products AS t1 JOIN complaints AS t2 ON t1.product_id = t2.product_id JOIN customers AS t3 GROUP BY t3.customer_id ORDER BY count(*) LIMIT 1`
- **FP** `theme_gallery` [empty] extra_join  pool_correct=True hint_correct=False
  - Q: Show theme and year for all exhibitions with ticket prices lower than 15.
  - FINAL: `SELECT e.Theme, e.Year FROM exhibition e JOIN exhibition_record er ON e.Exhibition_ID = er.Exhibition_ID WHERE e.Ticket_Price < 15;`
  - GOLD: `SELECT theme , YEAR FROM exhibition WHERE ticket_price < 15`
- **FP** `local_govt_mdm` [1row] extra_join, count_distinct  pool_correct=True hint_correct=False
  - Q: How many council taxes are collected for renting arrears ?
  - FINAL: `SELECT COUNT(DISTINCT r.council_tax_id) FROM Rent_Arrears r JOIN Council_Tax ct ON r.council_tax_id = ct.council_tax_id;`
  - GOLD: `SELECT count(*) FROM rent_arrears`
- **FP** `insurance_policies` [empty] extra_join, distinct, extra_filter, set_union, order, projection_arity, aggregate  pool_correct=True hint_correct=False
  - Q: Which claims caused more than 2 settlements or have the maximum claim value? List the date the claim was made and the claim id.
  - FINAL: `SELECT Claims.Date_Claim_Made, Claims.Claim_ID FROM Claims JOIN Payments ON Claims.Claim_ID = Payments.Settlement_ID JOIN Settlements ON Payments.Settlement_ID = Settlements.Settlement_ID WHERE Payments.Amount_Payment > 2 OR Payments.Amount_Payment = (SELECT MAX(Amount_Payment) FROM Payments) ORDER BY Claims.Date_Claim_Made`
  - GOLD: `SELECT T1.Date_Claim_Made , T1.Claim_id FROM Claims AS T1 JOIN Settlements AS T2 ON T1.Claim_id = T2.Claim_id GROUP BY T1.Claim_id HAVING count(*) > 2 UNION SELECT T1.Date_Claim_Made , T1.Claim_id FROM Claims AS T1 JOIN Settlements AS T2 ON T1.Claim_id = T2.Claim_id WHERE T1.Amount_Claimed = ( SELECT max(Amount_Claimed) FROM Claims )`
- **FP** `insurance_policies` [empty] extra_join, group_key, aggregate  pool_correct=False hint_correct=False
  - Q: Find the claim id and claim date of the claim that incurred the most settlement count. Also tell me the count.
  - FINAL: `SELECT Claims.Claim_ID, Claims.Date_Claim_Made, COUNT(Payments.Settlement_ID) AS settlement_count FROM Claims JOIN Settlements ON Claims.Claim_ID = Settlements.Claim_ID JOIN Payments ON Settlements.Settlement_ID = Payments.Settlement_ID GROUP BY Claims.Claim_ID, Claims.Date_Claim_Made ORDER BY settlement_count DESC LIMIT 1;`
  - GOLD: `SELECT T1.claim_id , T1.date_claim_made , count(*) FROM Claims AS T1 JOIN Settlements AS T2 ON T1.claim_id = T2.claim_id GROUP BY T1.claim_id ORDER BY count(*) DESC LIMIT 1`
- **FP** `local_govt_in_alabama` [1row] extra_join, grouping, order  pool_correct=False hint_correct=False
  - Q: What are all the distinct participant ids who attended any events?
  - FINAL: `SELECT COUNT(DISTINCT "Participants"."Participant_ID") FROM "Participants" JOIN "Participants_in_Events" ON "Participants"."Participant_ID" = "Participants_in_Events"."Participant_ID" JOIN "Events" ON "Participants_in_Events"."Event_ID" = "Events"."Event_ID" GROUP BY "Participants"."Participant_ID" ORDER BY "Participants"."Participant_ID"`
  - GOLD: `SELECT count(DISTINCT participant_id) FROM participants_in_Events`
- **FP** `workshop_paper` [1row] extra_join, literal_value  pool_correct=False hint_correct=False
  - Q: Show the names of authors from college "Florida" or "Temple"
  - FINAL: `SELECT submission.Author FROM submission JOIN Acceptance ON submission.Submission_ID = Acceptance.Submission_ID JOIN workshop ON Acceptance.Workshop_ID = workshop.Workshop_ID WHERE submission.College IN ('Florida', 'Temple');`
  - GOLD: `SELECT Author FROM submission WHERE College = "Florida" OR College = "Temple"`
- **FP** `restaurant_1` [empty] extra_join, literal_value, extra_filter  pool_correct=False hint_correct=False
  - Q: When did Linda Smith visit Subway?
  - FINAL: `SELECT v.Time FROM Visits_Restaurant AS v JOIN Student AS s ON v.StuID = s.StuID JOIN Restaurant AS r ON v.ResID = r.ResID JOIN "Type_Of_Restaurant" AS "_repair_fk_1" ON "r"."ResID" = "_repair_fk_1"."ResID" JOIN Restaurant_Type AS rt ON "_repair_fk_1"."ResTypeID" = "rt"."ResTypeID" WHERE s.LName = 'Smith' AND s.Fname = 'Linda' AND r.ResName = 'Subway' AND rt.ResTypeName = 'Type of Restaurant' AND `
  - GOLD: `SELECT TIME FROM Student JOIN Visits_Restaurant ON Student.StuID = Visits_Restaurant.StuID JOIN Restaurant ON Visits_Restaurant.ResID = Restaurant.ResID WHERE Student.Fname = "Linda" AND Student.Lname = "Smith" AND Restaurant.ResName = "Subway";`
- **FP** `tracking_orders` [empty] extra_join, literal_value, extra_filter, set_intersect, projection_arity  pool_correct=False hint_correct=False
  - Q: Find the names of the customers who have order status both "On Road" and "Shipped".
  - FINAL: `SELECT DISTINCT Customers.customer_name FROM Customers JOIN Orders ON Customers.customer_id = Orders.customer_id WHERE Orders.order_status = 'On Road' AND EXISTS ( SELECT 1 FROM Order_Items WHERE Order_Items.order_id = Orders.order_id AND Order_Items.order_item_status = 'Shipped' );`
  - GOLD: `SELECT T1.customer_name FROM customers AS T1 JOIN orders AS T2 ON T1.customer_id = T2.customer_id WHERE T2.order_status = "On Road" INTERSECT SELECT T1.customer_name FROM customers AS T1 JOIN orders AS T2 ON T1.customer_id = T2.customer_id WHERE T2.order_status = "Shipped"`
- **FP** `roller_coaster` [empty] extra_join, literal_value, like_vs_eq  pool_correct=True hint_correct=True
  - Q: List the names of countries whose language is not "German".
  - FINAL: `SELECT c.Name FROM country AS c JOIN roller_coaster AS rc ON c.Country_ID = rc.Country_ID WHERE NOT c.Languages LIKE '%German%'`
  - GOLD: `SELECT Name FROM country WHERE Languages != "German"`
- **FP** `tracking_grants_for_research` [empty] extra_join, literal_value, missing_filter  pool_correct=False hint_correct=False
  - Q: What are the staff roles of the staff who
  - FINAL: `SELECT Staff_Roles.role_code FROM Staff_Roles JOIN Project_Staff ON Staff_Roles.role_code = Project_Staff.role_code JOIN "Projects" AS "_repair_fk_1" ON "Project_Staff"."project_id" = "_repair_fk_1"."project_id" JOIN "Organisations" AS "_repair_fk_2" ON "_repair_fk_1"."organisation_id" = "_repair_fk_2"."organisation_id" JOIN Research_Staff ON "_repair_fk_2"."organisation_id" = "Research_Staff"."em`
  - GOLD: `SELECT role_code FROM Project_Staff WHERE date_from > '2003-04-19 15:06:20' AND date_to < '2016-03-15 00:33:18'`
- **FP** `customers_and_addresses` [1row] extra_join, missing_table, literal_value  pool_correct=False hint_correct=False
  - Q: How many types of products have Rodrick Heaney bought in total?
  - FINAL: `SELECT COUNT(DISTINCT address_type) AS product_types FROM Customer_Orders JOIN Customer_Addresses ON Customer_Orders.customer_id = Customer_Addresses.address_id JOIN Customers ON Customer_Addresses.customer_id = Customers.customer_id WHERE customer_name = 'Rodrick Heaney';`
  - GOLD: `SELECT count(DISTINCT t3.product_id) FROM customers AS t1 JOIN customer_orders AS t2 ON t1.customer_id = t2.customer_id JOIN order_items AS t3 ON t2.order_id = t3.order_id WHERE t1.customer_name = "Rodrick Heaney"`
- **FP** `twitter_1` [empty] group_key  pool_correct=False hint_correct=False
  - Q: Find the name and email for the users who have more than one follower.
  - FINAL: `SELECT up.name, up.email FROM user_profiles up JOIN follows f ON up.uid = f.f2 GROUP BY up.uid HAVING COUNT(f.f1) > 1;`
  - GOLD: `SELECT T1.name , T1.email FROM user_profiles AS T1 JOIN follows AS T2 ON T1.uid = T2.f1 GROUP BY T2.f1 HAVING count(*) > 1`
- **FP** `network_2` [empty] literal_case_space  pool_correct=False hint_correct=False
  - Q: Find the name and age of all males in order of their age.
  - FINAL: `SELECT name FROM Person WHERE gender = 'Male' ORDER BY age ASC`
  - GOLD: `SELECT name FROM Person WHERE gender = 'male' ORDER BY age`
- **FP** `local_govt_mdm` [empty] literal_case_space  pool_correct=True hint_correct=False
  - Q: What are the distinct cross reference source system codes which are related to the master customer details 'Gottlieb, Becker and Wyman'?
  - FINAL: `SELECT DISTINCT CMI_Cross_References.source_system_code FROM CMI_Cross_References JOIN Customer_Master_Index ON CMI_Cross_References.master_customer_id = Customer_Master_Index.master_customer_id WHERE Customer_Master_Index.cmi_details = 'Gottlieb, Becker and Wyman';`
  - GOLD: `SELECT DISTINCT T2.source_system_code FROM customer_master_index AS T1 JOIN cmi_cross_references AS T2 ON T1.master_customer_id = T2.master_customer_id WHERE T1.cmi_details = 'Gottlieb , Becker and Wyman'`
- **FP** `music_4` [empty] literal_value  pool_correct=False hint_correct=False
  - Q: What are the songs in volumes that have resulted in a nomination at music festivals?
  - FINAL: `SELECT volume.Song FROM volume JOIN music_festival ON "volume"."Volume_ID" = "music_festival"."Volume" WHERE music_festival.Result = 'Nomination'`
  - GOLD: `SELECT T2.Song FROM music_festival AS T1 JOIN volume AS T2 ON T1.Volume = T2.Volume_ID WHERE T1.Result = "Nominated"`
- **FP** `tracking_software_problems` [empty] literal_value, aggregate  pool_correct=False hint_correct=False
  - Q: Which problems were reported before the date of any problem reported by the staff Lysanne Turcotte? Give me the ids of the problems.
  - FINAL: `SELECT problem_id FROM Problems WHERE reported_by_staff_id = (SELECT staff_id FROM Staff WHERE staff_first_name = 'Lysanne Turcotte' AND staff_last_name = 'Turcotte');`
  - GOLD: `SELECT T1.problem_id FROM problems AS T1 JOIN staff AS T2 ON T1.reported_by_staff_id = T2.staff_id WHERE date_problem_reported < ( SELECT min(date_problem_reported) FROM problems AS T3 JOIN staff AS T4 ON T3.reported_by_staff_id = T4.staff_id WHERE T4.staff_first_name = "Lysanne" AND T4.staff_last_name = "Turcotte" )`
- **FP** `local_govt_mdm` [empty] literal_value, like_vs_eq  pool_correct=False hint_correct=False
  - Q: What are the renting arrears tax ids related to the customer master index whose detail is not 'Schmidt, Kertzmann and Lubowitz'?
  - FINAL: `SELECT r.council_tax_id FROM Rent_Arrears AS r JOIN CMI_Cross_References AS c ON r.cmi_cross_ref_id = c.cmi_cross_ref_id JOIN Customer_Master_Index AS cm ON c.master_customer_id = cm.master_customer_id WHERE NOT cm.cmi_details LIKE '%Schmidt, Kertzmann and Lubowitz%'`
  - GOLD: `SELECT T1.council_tax_id FROM Rent_Arrears AS T1 JOIN CMI_Cross_References AS T2 ON T1.cmi_cross_ref_id = T2.cmi_cross_ref_id JOIN Customer_Master_Index AS T3 ON T3.master_customer_id = T2.master_customer_id WHERE T3.cmi_details != 'Schmidt , Kertzmann and Lubowitz'`
- **FP** `loan_1` [1row] missing_filter  pool_correct=False hint_correct=False
  - Q: What is the average credit score for customers who have taken a loan?
  - FINAL: `SELECT AVG(customer.credit_score) AS average_credit_score FROM customer JOIN loan ON customer.cust_ID = loan.cust_ID;`
  - GOLD: `SELECT avg(credit_score) FROM customer WHERE cust_id IN (SELECT cust_id FROM loan)`
- **FP** `college_1` [1row] missing_table  pool_correct=False hint_correct=False
  - Q: How many students enrolled in class ACCT-211?
  - FINAL: `SELECT COUNT(*) AS STUDENTS_ENROLLED FROM ENROLL WHERE CLASS_CODE = 'ACCT-211';`
  - GOLD: `SELECT count(*) FROM CLASS AS T1 JOIN enroll AS T2 ON T1.class_code = T2.class_code WHERE T1.crs_code = 'ACCT-211'`
- **FP** `products_gen_characteristics` [1row] missing_table, count_distinct, group_key  pool_correct=False hint_correct=False
  - Q: Return the name of the characteristic that is most common across all products.
  - FINAL: `SELECT Characteristics.characteristic_name FROM Characteristics JOIN Product_Characteristics ON Characteristics.characteristic_id = Product_Characteristics.characteristic_id GROUP BY Characteristics.characteristic_id ORDER BY COUNT(DISTINCT Product_Characteristics.product_id) DESC LIMIT 1;`
  - GOLD: `SELECT t3.characteristic_name FROM products AS t1 JOIN product_characteristics AS t2 ON t1.product_id = t2.product_id JOIN CHARACTERISTICS AS t3 ON t2.characteristic_id = t3.characteristic_id GROUP BY t3.characteristic_name ORDER BY count(*) DESC LIMIT 1`
- **FP** `product_catalog` [empty] missing_table, literal_value  pool_correct=True hint_correct=False
  - Q: Which attribute definitions have attribute value 0? Give me the attribute name and attribute ID.
  - FINAL: `SELECT attribute_name, attribute_id FROM Attribute_Definitions WHERE attribute_data_type = '0'`
  - GOLD: `SELECT t1.attribute_name , t1.attribute_id FROM Attribute_Definitions AS t1 JOIN Catalog_Contents_Additional_Attributes AS t2 ON t1.attribute_id = t2.attribute_id WHERE t2.attribute_value = 0`
- **FP** `club_1` [empty] missing_table, literal_value, aggregate  pool_correct=False hint_correct=False
  - Q: Which club has the most members majoring in "600"?
  - FINAL: `SELECT "Club"."ClubName" FROM "Club" JOIN "Member_of_club" ON "Club"."ClubID" = "Member_of_club"."ClubID" WHERE "Member_of_club"."Position" = '600' GROUP BY "Club"."ClubName" HAVING COUNT("Member_of_club"."StuID") > 0 ORDER BY COUNT(*) DESC LIMIT 1`
  - GOLD: `SELECT t1.clubname FROM club AS t1 JOIN member_of_club AS t2 ON t1.clubid = t2.clubid JOIN student AS t3 ON t2.stuid = t3.stuid WHERE t3.major = "600" GROUP BY t1.clubname ORDER BY count(*) DESC LIMIT 1`
- **FP** `college_1` [empty] other_semantic  pool_correct=False hint_correct=False
  - Q: How many classes exist for each school?
  - FINAL: `SELECT DEPARTMENT.SCHOOL_CODE, COUNT(CLASS.CLASS_CODE) AS number_of_classes_per_school FROM CLASS JOIN COURSE ON CLASS.CRS_CODE = COURSE.CRS_CODE JOIN DEPARTMENT ON COURSE.DEPT_CODE = DEPARTMENT.DEPT_CODE GROUP BY DEPARTMENT.SCHOOL_CODE;`
  - GOLD: `SELECT count(*) , T3.school_code FROM CLASS AS T1 JOIN course AS T2 ON T1.crs_code = T2.crs_code JOIN department AS T3 ON T2.dept_code = T3.dept_code GROUP BY T3.school_code`
- **FP** `soccer_2` [empty] other_semantic  pool_correct=True hint_correct=True
  - Q: Find the name and hours of the students whose tryout decision is yes.
  - FINAL: `SELECT Player.pName, Player.HS FROM Player JOIN Tryout ON Player.pID = Tryout.pID WHERE "Player"."yCard" = 'yes'`
  - GOLD: `SELECT T1.pName , T1.HS FROM player AS T1 JOIN tryout AS T2 ON T1.pID = T2.pID WHERE T2.decision = 'yes'`
- **FP** `csu_1` [empty] other_semantic  pool_correct=False hint_correct=False
  - Q: What are the campuses that had between 600 and 1000 faculty members in 2004?
  - FINAL: `SELECT Campuses.Id AS Campus FROM Campuses JOIN faculty ON Campuses.Id = faculty.Campus WHERE faculty.Year = 2004 AND faculty.Faculty >= 600 AND faculty.Faculty <= 1000;`
  - GOLD: `SELECT T1.campus FROM campuses AS t1 JOIN faculty AS t2 ON t1.id = t2.campus WHERE t2.faculty >= 600 AND t2.faculty <= 1000 AND T1.year = 2004`
- **FP** `e_government` [1row] other_semantic  pool_correct=False hint_correct=True
  - Q: What is the last name of the first individual contacted from the organization with the maximum UK Vat number across all organizations?
  - FINAL: `SELECT i.individual_last_name FROM Individuals i JOIN Organization_Contact_Individuals oci ON i.individual_id = oci.individual_id JOIN Organizations o ON oci.organization_id = o.organization_id WHERE o.uk_vat_number = (SELECT MAX(uk_vat_number) FROM Organizations) ORDER BY oci.date_contact_from LIMIT 1;`
  - GOLD: `SELECT t3.individual_last_name FROM organizations AS t1 JOIN organization_contact_individuals AS t2 ON t1.organization_id = t2.organization_id JOIN individuals AS t3 ON t2.individual_id = t3.individual_id WHERE t1.uk_vat_number = (SELECT max(uk_vat_number) FROM organizations) ORDER BY t2.date_contact_to ASC LIMIT 1`
- **NM** `movie_1` [multi] count_distinct, grouping, order, aggregate  pool_correct=False hint_correct=False
  - Q: For each director who directed more than one movie, what are the titles and dates of release for all those movies?
  - FINAL: `SELECT m.title, m.year FROM Movie m WHERE m.director IS NOT NULL GROUP BY m.director HAVING COUNT(DISTINCT m.mID) > 1 ORDER BY m.title;`
  - GOLD: `SELECT T1.title , T1.year FROM Movie AS T1 JOIN Movie AS T2 ON T1.director = T2.director WHERE T1.title != T2.title`
- **NM** `browser_web` [multi] distinct, extra_filter, set_except, projection_arity  pool_correct=False hint_correct=False
  - Q: Show the accelerator names and supporting operating systems that are not compatible with the browser named 'Opera'.
  - FINAL: `SELECT accelerator.name, accelerator.Operating_system FROM Web_client_accelerator accelerator LEFT JOIN accelerator_compatible_browser ON accelerator.id = accelerator_compatible_browser.accelerator_id LEFT JOIN browser ON accelerator_compatible_browser.browser_id = browser.id WHERE browser.name != 'Opera';`
  - GOLD: `SELECT name , operating_system FROM web_client_accelerator EXCEPT SELECT T1.name , T1.operating_system FROM web_client_accelerator AS T1 JOIN accelerator_compatible_browser AS T2 ON T2.accelerator_id = T1.id JOIN browser AS T3 ON T2.browser_id = T3.id WHERE T3.name = 'Opera'`
- **NM** `college_3` [multi] distinct, literal_value, extra_filter, set_union, projection_arity  pool_correct=False hint_correct=False
  - Q: Find the names of courses that have either 3 credits or 1 credit but 4 hours.
  - FINAL: `SELECT C.CName FROM Course C WHERE C.Credits IN (3, 1) AND C.Hours = '4';`
  - GOLD: `SELECT CName FROM COURSE WHERE Credits = 3 UNION SELECT CName FROM COURSE WHERE Credits = 1 AND Hours = 4`
- **NM** `tracking_grants_for_research` [multi] distinct, literal_value, extra_filter, set_union, projection_arity  pool_correct=False hint_correct=False
  - Q: List from which date and to which date these staff work: project staff of the project which hires the most staffs
  - FINAL: `SELECT ps.date_from, ps.date_to FROM Project_Staff ps WHERE ps.project_id = (SELECT ps2.project_id FROM Project_Staff ps2 GROUP BY ps2.project_id ORDER BY COUNT(*) DESC LIMIT 1);`
  - GOLD: `SELECT date_from , date_to FROM Project_Staff WHERE project_id IN( SELECT project_id FROM Project_Staff GROUP BY project_id ORDER BY count(*) DESC LIMIT 1 ) UNION SELECT date_from , date_to FROM Project_Staff WHERE role_code = 'leader'`
- **NM** `flight_company` [1row] extra_join, aggregate  pool_correct=False hint_correct=False
  - Q: What is the velocity of the pilot named 'Thompson'?
  - FINAL: `SELECT flight.Velocity AS pilot_velocity FROM flight INNER JOIN operate_company ON flight.airport_id = operate_company.id WHERE operate_company.name = 'Thompson';`
  - GOLD: `SELECT avg(velocity) FROM flight WHERE pilot = 'Thompson'`
- **NM** `shop_membership` [empty] extra_join, count_distinct, extra_filter, set_except, projection_arity, aggregate  pool_correct=False hint_correct=False
  - Q: Show all cities without a branch having more than 100 memberships.
  - FINAL: `SELECT DISTINCT b.City FROM branch b WHERE NOT EXISTS ( SELECT 1 FROM membership_register_branch mrb JOIN purchase p ON mrb.Branch_ID = p.Branch_ID AND mrb.Member_ID = p.Member_ID WHERE mrb.Branch_ID = b.Branch_ID GROUP BY mrb.Branch_ID HAVING COUNT(DISTINCT mrb.Member_ID) > 100 );`
  - GOLD: `SELECT city FROM branch EXCEPT SELECT city FROM branch WHERE membership_amount > 100`
- **NM** `bike_1` [multi] extra_join, group_key  pool_correct=False hint_correct=False
  - Q: Find the ids and names of stations from which at least 200 trips started.
  - FINAL: `SELECT station.id, station.name FROM station JOIN trip ON station.id = trip.start_station_id GROUP BY station.id HAVING COUNT(trip.id) >= 200;`
  - GOLD: `SELECT start_station_id , start_station_name FROM trip GROUP BY start_station_name HAVING COUNT(*) >= 200`
- **NM** `behavior_monitoring` [1row] extra_join, missing_table  pool_correct=False hint_correct=False
  - Q: How many distinct incident type codes are there?
  - FINAL: `SELECT COUNT(DISTINCT Ref_Incident_Type.incident_type_code) FROM Ref_Incident_Type;`
  - GOLD: `SELECT count(DISTINCT incident_type_code) FROM Behavior_Incident`
- **NM** `train_station` [empty] literal_value  pool_correct=False hint_correct=False
  - Q: Find the names of the trains that do not pass any station located in London.
  - FINAL: `SELECT train.Name FROM train WHERE NOT EXISTS ( SELECT 1 FROM train_station JOIN station ON train_station.Station_ID = station.Station_ID WHERE train_station.Train_ID = train.Train_ID AND station.Location = 'London' );`
  - GOLD: `SELECT T2.name FROM train_station AS T1 JOIN train AS T2 ON T1.train_id = T2.train_id WHERE T1.station_id NOT IN (SELECT T4.station_id FROM train_station AS T3 JOIN station AS T4 ON T3.station_id = T4.station_id WHERE t4.location = "London")`
- **NM** `hr_1` [empty] missing_table  pool_correct=False hint_correct=False
  - Q: What are all the employee ids and the names of the countries in which they work?
  - FINAL: `SELECT employees.EMPLOYEE_ID, countries.COUNTRY_NAME FROM employees JOIN countries ON employees.COUNTRY_ID = countries.COUNTRY_ID;`
  - GOLD: `SELECT T1.employee_id , T4.country_name FROM employees AS T1 JOIN departments AS T2 ON T1.department_id = T2.department_id JOIN locations AS T3 ON T2.location_id = T3.location_id JOIN countries AS T4 ON T3.country_id = T4.country_id`
- **NM** `local_govt_in_alabama` [multi] missing_table, distinct, literal_value, extra_filter, set_except, like_vs_eq, projection_arity  pool_correct=False hint_correct=False
  - Q: Which events id does not have any participant with detail 'Kenyatta Kuhn'?
  - FINAL: `SELECT Event_ID FROM Events WHERE Event_Details LIKE '%Kenyatta Kuhn%';`
  - GOLD: `SELECT event_id FROM EVENTS EXCEPT SELECT T1.event_id FROM Participants_in_Events AS T1 JOIN Participants AS T2 ON T1.Participant_ID = T2.Participant_ID WHERE Participant_Details = 'Kenyatta Kuhn'`
- **NM** `products_gen_characteristics` [1row] missing_table, literal_value, like_vs_eq  pool_correct=False hint_correct=False
  - Q: How many products have their color described as 'white' or have a characteristic with the name 'hot'?
  - FINAL: `SELECT COUNT(*) FROM Products WHERE product_description LIKE '%white%' OR (SELECT characteristic_name FROM Product_Characteristics WHERE product_characteristic_value = 'hot') IS NOT NULL;`
  - GOLD: `SELECT count(*) FROM products AS t1 JOIN product_characteristics AS t2 ON t1.product_id = t2.product_id JOIN CHARACTERISTICS AS t3 ON t2.characteristic_id = t3.characteristic_id JOIN ref_colors AS t4 ON t1.color_code = t4.color_code WHERE t4.color_description = "white" OR t3.characteristic_name = "hot"`
- **NM** `election` [multi] other_semantic  pool_correct=False hint_correct=False
  - Q: For each party, return the name of the party and the number of delegates from that party.
  - FINAL: `SELECT party.Party, COUNT(party.Party_ID) AS delegate_count FROM party JOIN election ON party.Party_ID = election.Party GROUP BY party.Party;`
  - GOLD: `SELECT T2.Party , COUNT(*) FROM election AS T1 JOIN party AS T2 ON T1.Party = T2.Party_ID GROUP BY T1.Party`
- **NM** `network_2` [1row] unparsed  pool_correct=False hint_correct=False
  - Q: How many people are older than every engineer?
  - FINAL: `SELECT COUNT(*) FROM Person WHERE age > (SELECT age FROM PersonFriend WHERE friend = Person.name AND year = (SELECT MAX(year) FROM PersonFriend WHERE friend = Person.name AND year = (SELECT MAX(year) FROM PersonFriend WHERE friend = Person.name AND year = (SELECT MAX(year) FROM PersonFriend WHERE friend = Person.name AND year = (SELECT MAX(year) FROM PersonFriend WHERE friend = Person.name AND yea`
  - GOLD: `SELECT count(*) FROM Person WHERE age > (SELECT max(age) FROM person WHERE job = 'engineer')`
