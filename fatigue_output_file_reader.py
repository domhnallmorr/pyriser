

class FatigueOutputFile:
	def __init__(self, output_file):
		self.output_file = output_file
		self.setup_variables()
		self.read_output_file()
		self.parse_output_file()
	
	def setup_variables(self):
		self.fatigue_lives = []
		
	def read_output_file(self):
		
		with open(self.output_file) as f:
			self.data = f.readlines()
			
	def parse_output_file(self):
		section = None
		
		for idx, line in enumerate(self.data):
			if 'Results in Plot Format' in line:
				section = 'fatigue lives'
				
			if section == 'fatigue lives':
				line = line.split()
				
				if len(line) == 9:
					line = [int(line[0]), int(line[1]), float(line[2]), float(line[3]), int(line[4]), float(line[5]), int(line[6]), float(line[7]), int(line[8])]
					self.fatigue_lives.append(line)
		
if __name__ == '__main__':
	
	# files = [
		# r"Z:\114-Projects\OP212429-Flemish Pass\02 VIV\03 VIM\8.56ppg\3-Lifetime\01 Casing\50pc NE\Lifetime_20in_Casing_Seam_Weld - C1-SW-CP SCF 1.0.out",
		# r"Z:\114-Projects\OP212429-Flemish Pass\02 VIV\03 VIM\8.56ppg\3-Lifetime\01 Casing\50pc NE\Lifetime_20in_Casing_Connector_Body - B1-SW-CP SCF 1.299.out",
		# r"Z:\114-Projects\OP212429-Flemish Pass\02 VIV\03 VIM\8.56ppg\3-Lifetime\01 Casing\50pc NE\Lifetime_20in_Casing_Connector_Weld - C1-SW-CP SCF 1.189.out",
	# ]
	
	
	files = [
		r"Z:\114-Projects\OP212429-Flemish Pass\02 VIV\03 VIM\11.0ppg\3-Lifetime\04 Riser\50pc NE\Lifetime_Riser_Seam_Weld - C-SW-CP SCF 1.0.out",
		r"Z:\114-Projects\OP212429-Flemish Pass\02 VIV\03 VIM\11.0ppg\3-Lifetime\04 Riser\50pc NE\Lifetime_Riser_Booster_Joint_Weld_Root - C1-FC SCF 1.538.out",
		r"Z:\114-Projects\OP212429-Flemish Pass\02 VIV\03 VIM\11.0ppg\3-Lifetime\04 Riser\50pc NE\Lifetime_Riser_Booster_Joint_Weld_Cap - C1-SW-CP SCF 2.310.out",
		r"Z:\114-Projects\OP212429-Flemish Pass\02 VIV\03 VIM\11.0ppg\3-Lifetime\04 Riser\50pc NE\Lifetime_Riser_Booster_Joint_Transition_Corner - B1-FC SCF 3.722.out",
		r"Z:\114-Projects\OP212429-Flemish Pass\02 VIV\03 VIM\11.0ppg\3-Lifetime\04 Riser\50pc NE\Lifetime_Riser_Pup_Joint_Weld_Root - C1-FC SCF 1.024.out",
		r"Z:\114-Projects\OP212429-Flemish Pass\02 VIV\03 VIM\11.0ppg\3-Lifetime\04 Riser\50pc NE\Lifetime_Riser_Pup_Joint_Weld_Cap - C1-SW-CP SCF 1.126.out",
		r"Z:\114-Projects\OP212429-Flemish Pass\02 VIV\03 VIM\11.0ppg\3-Lifetime\04 Riser\50pc NE\Lifetime_Riser_Pup_Joint_Handling_Groove - B1-FC SCF 1.771.out",
		r"Z:\114-Projects\OP212429-Flemish Pass\02 VIV\03 VIM\11.0ppg\3-Lifetime\04 Riser\50pc NE\Lifetime_Riser_Regular_Joint_Weld_Root - C1-FC SCF 1.043.out",
		r"Z:\114-Projects\OP212429-Flemish Pass\02 VIV\03 VIM\11.0ppg\3-Lifetime\04 Riser\50pc NE\Lifetime_Riser_Regular_Joint_Weld_Cap - C1-SW-CP SCF 1.171.out",
		r"Z:\114-Projects\OP212429-Flemish Pass\02 VIV\03 VIM\11.0ppg\3-Lifetime\04 Riser\50pc NE\Lifetime_Riser_Regular_Joint_Handling_Groove - B1-FC SCF 1.746.out",
		]
		
	lives = []
	for file in files:
		o = FatigueOutputFile(file)
		lives.append(o.fatigue_lives)
	
	
	for idx, row in enumerate(lives[0]):
		
		for file in lives:
			print(f"{file[idx][3]},", end='')
		print("")
	