# World facts
- train: 668665 rows x 15 cols; test: 286571 rows x 14 cols; no missing values in either
- train ids 0..668664 unique; test ids 668665..955235 unique; contiguous split
- target Will_Buy_EV: Yes/No; positive rate 0.174645 (sample sub fills all rows with this base rate)
- numeric features: Age, Annual_Income_USD, Daily_Commute_km, Number_of_Cars_Owned, Charging_Stations_Near_Home, Charging_Stations_Near_Work, Environmental_Concern_Level
- categorical features: Gender (Female/Male/Other), City_Type (Rural/Suburban/Urban), Current_Car_Type (Hatchback/SUV/Sedan/Truck), Home_Charging_Possible (No/Yes), Subsidy_Available (No/Yes), Range_Anxiety_Level (High/Low/Medium)
- target rate by Subsidy_Available: No 0.0058, Yes 0.2747 (strongest signal); by Range_Anxiety_Level: High 0.0014, Low 0.1890, Medium 0.0417; by Home_Charging_Possible: No 0.1271, Yes 0.1958
