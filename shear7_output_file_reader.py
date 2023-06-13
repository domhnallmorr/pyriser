


class Shear7OutputFile:
	def __init__(self, file, print_name=True, verbose=False):
	
		self.file = file
		self.verbose = verbose
		
		if print_name:
			print(file)
		
		self.setup_variables()
		self.read_file()
		
		if self.results_start_idx is None:
			print("Could Not Find Results in File")
		else:
			self.parse_possible_excited_modes()
		
	def setup_variables(self):
		self.no_possible_excitated_modes = None
		self.initial_power_calcs = {}
		self.results_start_idx = None
		self.power_calc_start_idx = None
		
	def read_file(self):
	
		with open(self.file) as f:
			self.data = f.readlines()			
			
		for idx, line in enumerate(self.data):
			
			if "THE RESULTS OF PROGRAM ANALYSIS" in line:
				self.results_start_idx = idx
			
			if "F = force; L = length; T = time." in line:
				self.power_calc_start_idx = idx
				break
				
		
	def parse_possible_excited_modes(self):
		
		for i in range(self.power_calc_start_idx + 6, len(self.data)-1):
			
			if self.data[i].rstrip().strip() != "":
				line = self.data[i].rstrip().split()
				self.initial_power_calcs[int(line[0])] = {"freq_hz": float(line[1]), "Modal Power": float(line[4]), "Power Ratio Raised Exponent": float(line[6])}
				
			else:
				break
	
		self.no_possible_excitated_modes = int(self.data[i+1].rstrip().split()[-1])
		
		if self.verbose:
			print(f"No of Possible Excited Modes: {self.no_possible_excitated_modes}")
				
if __name__ == "__main__":
	
	s = Shear7OutputFile(r"Z:\114-Projects\OP211828 Tullow Oil - Dropped Riser and Transit Assessment\01 VIV Transit Fatigue\Conductor - Con Body - 1500m\Cond-Con_Body-1500m-1Yr-0.5kn.out", verbose=True)
	
			